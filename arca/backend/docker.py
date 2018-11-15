import hashlib
import json
import platform
import signal
import tarfile
import time

from io import BytesIO
from pathlib import Path
from typing import Optional, List, Tuple, Union, Callable

try:
    import docker
    import docker.errors
except ImportError:
    docker = None

from git import Repo
from requests.exceptions import ConnectionError

import arca
from arca.exceptions import ArcaMisconfigured, BuildError, PushToRegistryError, BuildTimeoutError
from arca.result import Result
from arca.task import Task
from arca.utils import logger, LazySettingProperty
from .base import BaseBackend, RequirementsOptions


class DockerBackend(BaseBackend):
    """ Runs the tasks in Docker containers.

    Available settings:

    * **python_version** - set a specific version, current env. python version by default
    * **keep_container_running** - stop the container right away (default) or keep it running
    * **apt_dependencies** - a list of dependencies to install via ``apt-get``
    * **disable_pull** - build all locally
    * **inherit_image** - instead of using the default base Arca image, use this one
    * **use_registry_name** - use this registry to store images with requirements and dependencies
    * **registry_pull_only** - only use the registry to pull images, don't push updated
    """

    python_version = LazySettingProperty(default=None)
    keep_container_running = LazySettingProperty(default=False)
    apt_dependencies = LazySettingProperty(default=None)
    disable_pull = LazySettingProperty(default=False)  # so the build can be tested
    inherit_image = LazySettingProperty(default=None)
    use_registry_name = LazySettingProperty(default=None)
    registry_pull_only = LazySettingProperty(default=False)

    INSTALL_REQUIREMENTS = """
        FROM {name}:{tag}

        ADD {requirements_files} /srv/{target_file}

        WORKDIR /srv/

        RUN if grep -q Alpine /etc/issue; then \
                timeout -t {timeout} {install_cmd} {cmd_arguments}; \
            else \
                timeout {timeout} {install_cmd} {cmd_arguments}; \
            fi

        WORKDIR /home/arca
    """

    INSTALL_DEPENDENCIES = """
        FROM {name}:{tag}
        USER root
        RUN apt-get update && \
            apt-get install --no-install-recommends -y --autoremove {dependencies} && \
            apt-get clean
        USER arca
    """

    def __init__(self, **kwargs):
        """ Initializes the instance and checks that the docker package is installed.
        """
        super().__init__(**kwargs)

        if docker is None:
            raise ArcaMisconfigured(ArcaMisconfigured.PACKAGE_MISSING.format("docker"))

        self._containers = set()
        self.client = None
        self.alpine_inherited = None

    def validate_configuration(self):
        """
        Validates the provided settings.

        * Checks ``inherit_image`` format.
        * Checks ``use_registry_name`` format.
        * Checks that ``apt_dependencies`` is not set when ``inherit_image`` is set.

        :raise ArcaMisconfigured: If some of the settings aren't valid.
        """
        super().validate_configuration()

        if self.inherit_image is not None:
            try:
                assert len(str(self.inherit_image).split(":")) == 2
            except (ValueError, AssertionError):
                raise ArcaMisconfigured(f"Image '{self.inherit_image}' is not a valid value for the 'inherit_image'"
                                        f"setting")

        if self.inherit_image is not None and self.get_dependencies() is not None:
            raise ArcaMisconfigured("An external image is used as a base image, "
                                    "therefore Arca can't install dependencies.")

        if self.use_registry_name is not None:
            try:
                assert 2 >= len(str(self.inherit_image).split("/")) <= 3
            except ValueError:
                raise ArcaMisconfigured(f"Registry '{self.use_registry_name}' is not valid value for the "
                                        f"'use_registry_name' setting.")

    def check_docker_access(self):
        """ Creates a :class:`DockerClient <docker.client.DockerClient>` for the instance and checks the connection.

        :raise BuildError: If docker isn't accessible by the current user.
        """
        try:
            if self.client is None:
                self.client = docker.from_env()
            self.client.ping()  # check that docker is running and user is permitted to access it
        except ConnectionError as e:
            logger.exception(e)
            raise BuildError("Docker is not running or the current user doesn't have permissions to access docker.")

    def get_dependencies(self) -> Optional[List[str]]:
        """ Returns the ``apt_dependencies`` setting to a standardized format.

        :raise ArcaMisconfigured: if the dependencies can't be converted into a list of strings
        :return: List of dependencies, ``None`` if there are none.
        """

        if not self.apt_dependencies:
            return None

        try:
            dependencies = list([str(x).strip() for x in self.apt_dependencies])
        except (TypeError, ValueError):
            raise ArcaMisconfigured("Apk dependencies can't be converted into a list of strings")

        if not len(dependencies):
            return None

        dependencies.sort()

        return dependencies

    def get_python_version(self) -> str:
        """ Returns either the specified version from settings or platform.python_version()
        """
        if self.python_version is None:
            python_version = platform.python_version()
        else:
            python_version = self.python_version

        return python_version

    def get_image_name(self,
                       repo_path: Path,
                       requirements_option: RequirementsOptions,
                       dependencies: Optional[List[str]]) -> str:
        """ Returns the name for images with installed requirements and dependencies.
        """
        if self.inherit_image is None:
            return self.get_arca_base_name()
        else:
            name, tag = str(self.inherit_image).split(":")

            return f"arca_{name}_{tag}"

    def get_dependencies_hash(self, dependencies):
        """ Returns a SHA1 hash of the dependencies for usage in image names/tags.
        """
        return hashlib.sha256(bytes(",".join(dependencies), "utf-8")).hexdigest()

    def get_image_tag(self,
                      requirements_option: RequirementsOptions,
                      requirements_hash: Optional[str],
                      dependencies: Optional[List[str]]) -> str:
        """ Returns the tag for images with the dependencies and requirements installed.

        64-byte hexadecimal strings cannot be used as docker tags, so the prefixes are necessary.
        Double hashing the dependencies and requirements hash to make the final tag shorter.

        Prefixes:

        * Image type:

          * i – Inherited image
          * a – Arca base image

        * Requirements:

          * r – Does have some kind of requirements
          * s – Doesn't have requirements

        * Dependencies:

          * d – Does have dependencies
          * e – Doesn't have dependencies

        Possible outputs:

        * Inherited images:

          * `ise` – no requirements
          * `ide_<hash(requirements)>` – with requirements

        * From Arca base image:

          * `<Arca version>_<Python version>_ase` – no requirements and no dependencies
          * `<Arca version>_<Python version>_asd_<hash(dependencies)>` – only dependencies
          * `<Arca version>_<Python version>_are_<hash(requirements)>` – only requirements
          * `<Arca version>_<Python version>_ard_<hash(hash(dependencies) + hash(requirements))>`
            – both requirements and dependencies

        """
        prefix = ""

        if self.inherit_image is None:
            prefix = "{}_{}_".format(arca.__version__, self.get_python_version())

        prefix += "i" if self.inherit_image is not None else "a"
        prefix += "r" if requirements_option != RequirementsOptions.no_requirements else "s"
        prefix += "d" if dependencies is not None else "e"

        if self.inherit_image is not None:
            if requirements_hash:
                return prefix + "_" + requirements_hash
            return prefix

        if dependencies is None:
            dependencies_hash = ""
        else:
            dependencies_hash = self.get_dependencies_hash(dependencies)

        if requirements_hash and dependencies_hash:
            return prefix + "_" + hashlib.sha256(bytes(requirements_hash + dependencies_hash, "utf-8")).hexdigest()
        elif requirements_hash:
            return f"{prefix}_{requirements_hash}"
        elif dependencies_hash:
            return f"{prefix}_{dependencies_hash}"
        else:
            return prefix

    def get_arca_base_name(self):
        return "docker.io/mikicz/arca"

    def get_python_base_tag(self, python_version):
        return f"{arca.__version__}_{python_version}"

    def get_or_build_image(self, name: str, tag: str, dockerfile: Union[str, Callable[..., str]], *,
                           pull=True, build_context: Optional[Path]=None):
        """
        A proxy for commonly built images, returns them from the local system if they exist, tries to pull them if
        pull isn't disabled, otherwise builds them by the definition in ``dockerfile``.

        :param name: Name of the image
        :param tag: Image tag
        :param dockerfile: Dockerfile text or a callable (no arguments) that produces Dockerfile text
        :param pull: If the image is not present locally, allow pulling from registry (default is ``True``)
        :param build_context: A path to a folder. If it's provided, docker will build the image in the context
            of this folder. (eg. if ``ADD`` is needed)
        """
        if self.image_exists(name, tag):
            logger.info("Image %s:%s exists", name, tag)
            return

        elif pull:
            logger.info("Trying to pull image %s:%s", name, tag)

            try:
                self.client.images.pull(name, tag=tag)
                logger.info("The image %s:%s was pulled from registry", name, tag)
                return
            except docker.errors.APIError:
                logger.info("The image %s:%s can't be pulled, building locally.", name, tag)

        if callable(dockerfile):
            dockerfile = dockerfile()

        try:
            if build_context is None:
                fileobj = BytesIO(bytes(dockerfile, "utf-8"))  # required by the docker library

                self.client.images.build(
                    fileobj=fileobj,
                    tag=f"{name}:{tag}"
                )
            else:
                dockerfile_file = build_context / "dockerfile"
                dockerfile_file.write_text(dockerfile)

                self.client.images.build(
                    path=str(build_context.resolve()),
                    dockerfile=dockerfile_file.name,
                    tag=f"{name}:{tag}"
                )

                dockerfile_file.unlink()
        except docker.errors.BuildError as e:
            for line in e.build_log:
                if isinstance(line, dict) and line.get("errorDetail") and line["errorDetail"].get("code") in {124, 143}:
                    raise BuildTimeoutError(f"Installing of requirements timeouted after "
                                            f"{self.requirements_timeout} seconds.")

            logger.exception(e)

            raise BuildError("Building docker image failed, see extra info for details.", extra_info={
                "build_log": e.build_log
            })

    def get_arca_base(self, pull=True):
        """
        Returns the name and tag of image that has the basic build dependencies installed with just pyenv installed,
        with no python installed. (Builds or pulls the image if it doesn't exist locally.)
        """
        name = self.get_arca_base_name()
        tag = arca.__version__

        pyenv_installer = "https://raw.githubusercontent.com/pyenv/pyenv-installer/master/bin/pyenv-installer"
        dockerfile = f"""
            FROM debian:stretch-slim
            RUN apt-get update && \
                apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
                                   libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
                                   xz-utils tk-dev libffi-dev git locales && \
                apt-get clean

            RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen
            ENV LANG en_US.UTF-8
            ENV LANGUAGE en_US:en
            ENV LC_ALL en_US.UTF-8

            RUN adduser --system --disabled-password --shell /bin/bash arca

            USER arca
            WORKDIR /home/arca
            RUN echo "source $HOME/.bash_profile" >> .bashrc

            RUN curl -L {pyenv_installer} -o ~/pyenv-installer && \
                  /bin/bash ~/pyenv-installer && \
                  rm ~/pyenv-installer && \
                  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> /home/arca/.bash_profile && \
                  echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> /home/arca/.bash_profile && \
                  echo 'eval "$(pyenv init -)"' >> /home/arca/.bash_profile

            USER root

            RUN apt-get remove -y --autoremove curl && \
                apt-get clean -y

            RUN mkdir /srv/scripts

            USER arca

            SHELL ["bash", "-lc"]
            CMD bash -i
        """

        self.get_or_build_image(name, tag, dockerfile, pull=pull)
        return name, tag

    def get_python_base(self, python_version, pull=True):
        """
        Returns the name and tag of an image with specified ``python_version`` installed,
        if the image doesn't exist locally, it's pulled or built (extending the image from :meth:`get_arca_base`).
        """
        name = self.get_arca_base_name()
        tag = self.get_python_base_tag(python_version)

        def get_dockerfile():
            base_arca_name, base_arca_tag = self.get_arca_base(pull)

            return f"""
                FROM {base_arca_name}:{base_arca_tag}
                RUN pyenv update && \
                    pyenv install {python_version}
                ENV PYENV_VERSION {python_version}
                ENV PATH "/home/arca/.pyenv/shims:$PATH"
                RUN pip install --upgrade pip setuptools pipenv
                CMD bash -i
            """

        self.get_or_build_image(name, tag, get_dockerfile, pull=pull)

        return name, tag

    def get_inherit_image(self) -> Tuple[str, str]:
        """ Parses the ``inherit_image`` setting, checks if the image is present locally and pulls it otherwise.

        :return: Returns the name and the tag of the image.
        :raise ArcaMisconfiguration: If the image can't be pulled from registries.
        """
        name, tag = str(self.inherit_image).split(":")

        if self.image_exists(name, tag):
            return name, tag
        try:
            self.client.images.pull(name, tag)
        except docker.errors.APIError:
            raise ArcaMisconfigured(f"The specified image {self.inherit_image} from which Arca should inherit "
                                    f"can't be pulled")

        return name, tag

    def build_image_from_inherited_image(self, image_name: str, image_tag: str,
                                         repo_path: Path,
                                         requirements_option: RequirementsOptions):
        """
        Builds a image with installed requirements from the inherited image. (Or just tags the image
        if there are no requirements.)

        See :meth:`build_image` for parameters descriptions.

        :rtype: docker.models.images.Image
        """

        base_name, base_tag = self.get_inherit_image()

        if requirements_option == RequirementsOptions.no_requirements:
            image = self.get_image(base_name, base_tag)
            image.tag(image_name, image_tag)  # so ``build_image`` doesn't have to be called next time

            return image

        dockerfile = self.get_install_requirements_dockerfile(base_name, base_tag, repo_path, requirements_option)

        self.get_or_build_image(image_name, image_tag, dockerfile, build_context=repo_path.parent, pull=False)

        return self.get_image(image_name, image_tag)

    def get_image_with_installed_dependencies(self, image_name: str,
                                              dependencies: Optional[List[str]]) -> Tuple[str, str]:
        """
        Return name and tag of a image, based on the Arca python image, with installed dependencies defined
        by ``apt_dependencies``.

        :param image_name: Name of the image which will be ultimately used for the image.
        :param dependencies: List of dependencies in the standardized format.
        """
        python_version = self.get_python_version()

        if dependencies is not None:
            def install_dependencies_dockerfile():
                python_name, python_tag = self.get_python_base(python_version,
                                                               pull=not self.disable_pull)

                return self.INSTALL_DEPENDENCIES.format(
                    name=python_name,
                    tag=python_tag,
                    dependencies=" ".join(self.get_dependencies())
                )

            image_tag = self.get_image_tag(RequirementsOptions.no_requirements, None, dependencies)
            self.get_or_build_image(image_name, image_tag, install_dependencies_dockerfile,
                                    pull=not self.disable_pull)

            return image_name, image_tag
        else:
            return self.get_python_base(python_version, pull=not self.disable_pull)

    def build_image(self, image_name: str, image_tag: str,
                    repo_path: Path,
                    requirements_option: RequirementsOptions,
                    dependencies: Optional[List[str]]):
        """ Builds an image for specific requirements and dependencies, based on the settings.

        :param image_name: How the image should be named
        :param image_tag: And what tag it should have.
        :param repo_path: Path to the cloned repository.
        :param requirements_option: How requirements are set in the repository.
        :param dependencies: List of dependencies (in the formalized format)
        :return: The Image instance.
        :rtype: docker.models.images.Image
        """
        if self.inherit_image is not None:
            return self.build_image_from_inherited_image(image_name, image_tag, repo_path, requirements_option)

        if requirements_option == RequirementsOptions.no_requirements:

            python_version = self.get_python_version()

            # no requirements and no dependencies, just return the basic image with the correct python installed
            if dependencies is None:
                base_name, base_tag = self.get_python_base(python_version, pull=not self.disable_pull)
                image = self.get_image(base_name, base_tag)

                # tag the image so ``build_image`` doesn't have to be called next time
                image.tag(image_name, image_tag)

                return image

            # extend the image with correct python by installing the dependencies
            def install_dependencies_dockerfile():
                base_name, base_tag = self.get_python_base(python_version, pull=not self.disable_pull)

                return self.INSTALL_DEPENDENCIES.format(
                    name=base_name,
                    tag=base_tag,
                    dependencies=" ".join(dependencies)
                )

            self.get_or_build_image(image_name, image_tag, install_dependencies_dockerfile)

            return self.get_image(image_name, image_tag)

        else:  # doesn't have to be here, but the return right above was confusing
            def install_requirements_dockerfile():
                """ Returns a Dockerfile for installing pip requirements,
                    based on a image with installed dependencies (or no extra dependencies)
                """
                dependencies_name, dependencies_tag = self.get_image_with_installed_dependencies(image_name,
                                                                                                 dependencies)

                return self.get_install_requirements_dockerfile(
                    name=dependencies_name,
                    tag=dependencies_tag,
                    repo_path=repo_path,
                    requirements_option=requirements_option,
                )

            self.get_or_build_image(image_name, image_tag, install_requirements_dockerfile,
                                    build_context=repo_path.parent, pull=False)

            return self.get_image(image_name, image_tag)

    def push_to_registry(self, image, image_tag: str):
        """ Pushes a local image to a registry based on the ``use_registry_name`` setting.

        :type image: docker.models.images.Image
        :raise PushToRegistryError: If the push fails.
        """
        # already tagged, so it's already pushed
        if f"{self.use_registry_name}:{image_tag}" in image.tags:
            return

        image.tag(self.use_registry_name, image_tag)

        result = self.client.images.push(self.use_registry_name, image_tag)

        result = result.strip()  # remove empty line at the end of output

        # the last can have one of two outputs, either
        # {"progressDetail":{},"aux":{"Tag":"<tag>","Digest":"sha256:<hash>","Size":<size>}}
        # when the push is successful, or
        # {"errorDetail": {"message":"<error_msg>"},"error":"<error_msg>"}
        # when the push is not successful

        last_line = json.loads(result.split("\n")[-1])

        if "error" in last_line:
            self.client.images.remove(f"{self.use_registry_name}:{image_tag}")
            raise PushToRegistryError(f"Push of the image failed because of: {last_line['error']}", full_output=result)

        logger.info("Pushed image to registry %s:%s", self.use_registry_name, image_tag)
        logger.debug("Info:\n%s", result)

    def image_exists(self, image_name, image_tag):
        """ Returns if the image exists locally.
        """
        try:
            self.get_image(image_name, image_tag)
            return True
        except docker.errors.ImageNotFound:
            return False

    def get_image(self, image_name, image_tag):
        """ Returns a :class:`Image <docker.models.images.Image>` instance for the provided name and tag.

        :rtype: docker.models.images.Image
        """
        return self.client.images.get(f"{image_name}:{image_tag}")

    def try_pull_image_from_registry(self, image_name, image_tag):
        """
        Tries to pull a image with the tag ``image_tag`` from registry set by ``use_registry_name``.
        After the image is pulled, it's tagged with ``image_name``:``image_tag`` so lookup can
        be made locally next time.

        :return: A :class:`Image <docker.models.images.Image>` instance if the image exists, ``None`` otherwise.
        :rtype: Optional[docker.models.images.Image]
        """
        try:
            image = self.client.images.pull(self.use_registry_name, image_tag)
        except (docker.errors.ImageNotFound, docker.errors.NotFound):  # the image doesn't exist
            logger.info("Tried to pull %s:%s from a registry, not found", self.use_registry_name, image_tag)
            return None

        logger.info("Pulled %s:%s from registry, tagged %s:%s", self.use_registry_name, image_tag,
                    image_name, image_tag)

        # the name and tag are different on the repo, let's tag it with local name so exists checks run smoothly
        image.tag(image_name, image_tag)

        return image

    def container_running(self, container_name):
        """
        Finds out if a container with name ``container_name`` is running.

        :return: :class:`Container <docker.models.containers.Container>` if it's running, ``None`` otherwise.
        :rtype: Optional[docker.models.container.Container]
        """
        filters = {
            "name": container_name,
            "status": "running",
        }

        for container in self.client.containers.list(filters=filters):
            if container_name == container.name:
                return container
        return None

    def tar_files(self, path: Path) -> bytes:
        """ Returns a tar with the git repository.
        """
        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')
        tar.add(str(path), arcname="data", recursive=True)
        tar.close()
        return tarstream.getvalue()

    def tar_runner(self):
        """ Returns a tar with the runner script.
        """
        script_bytes = self.RUNNER.read_bytes()

        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')

        tarinfo = tarfile.TarInfo(name="runner.py")
        tarinfo.size = len(script_bytes)
        tarinfo.mtime = int(time.time())

        tar.addfile(tarinfo, BytesIO(script_bytes))
        tar.close()

        return tarstream.getvalue()

    def tar_task_definition(self, name: str, contents: str) -> bytes:
        """ Returns a tar with the task definition.

        :param name: Name of the file
        :param contents: Contens of the definition, utf-8
        """
        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')
        tarinfo = tarfile.TarInfo(name=name)

        script_bytes = contents.encode("utf-8")

        tarinfo.size = len(script_bytes)
        tarinfo.mtime = int(time.time())
        tar.addfile(tarinfo, BytesIO(script_bytes))
        tar.close()

        return tarstream.getvalue()

    def start_container(self, image, container_name: str, repo_path: Path):
        """ Starts a container with the image and name ``container_name`` and copies the repository into the container.

        :type image: docker.models.images.Image
        :rtype: docker.models.container.Container
        """
        command = "bash -i"

        if self.inherit_image:
            command = "sh -i"

        container = self.client.containers.run(image, command=command, detach=True, tty=True, name=container_name,
                                               working_dir=str((Path("/srv/data") / self.cwd).resolve()),
                                               auto_remove=True)

        container.exec_run(["mkdir", "-p", "/srv/scripts"])
        container.put_archive("/srv", self.tar_files(repo_path))
        container.put_archive("/srv/scripts", self.tar_runner())

        return container

    def get_image_for_repo(self, repo: str, branch: str, git_repo: Repo, repo_path: Path):
        """
        Returns an image for the specific repo (based on settings and requirements).

        1. Checks if the image already exists locally
        2. Tries to pull it from registry (if ``use_registry_name`` is set)
        3. Builds the image
        4. Pushes the image to registry so the image is available next time (if ``registry_pull_only`` is not set)

        See :meth:`run` for parameters descriptions.

        :rtype: docker.models.images.Image
        """
        requirements_option, requirements_hash = self.get_requirements_information(repo_path)
        dependencies = self.get_dependencies()

        logger.info("Getting image based on %s, %s", requirements_option, dependencies)

        image_name = self.get_image_name(repo_path, requirements_option, dependencies)
        image_tag = self.get_image_tag(requirements_option, requirements_hash, dependencies)

        logger.info("Using image %s:%s", image_name, image_tag)

        if self.image_exists(image_name, image_tag):
            image = self.get_image(image_name, image_tag)

            # in case the push to registry was set later and the image wasn't pushed when built
            if self.use_registry_name is not None and not self.registry_pull_only:
                self.push_to_registry(image, image_tag)

            return image

        if self.use_registry_name is not None:
            # the target image might have been built and pushed in a previous run already, let's try to pull it
            image = self.try_pull_image_from_registry(image_name, image_tag)

            if image is not None:  # image wasn't found
                return image

        image = self.build_image(image_name, image_tag, repo_path, requirements_option, dependencies)

        if self.use_registry_name is not None and not self.registry_pull_only:
            self.push_to_registry(image, image_tag)

        return image

    def get_container_name(self, repo: str, branch: str, git_repo: Repo):
        """ Returns the name of the container used for the repo.
        """
        return "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:
        """ Gets or builds an image for the repo, gets or starts a container for the image and runs the script.

        :param repo: Repository URL
        :param branch: Branch ane
        :param task: :class:`Task` to run.
        :param git_repo: :class:`Repo <git.repo.base.Repo>` of the cloned repository.
        :param repo_path: :class:`Path <pathlib.Path>` to the cloned location.
        """
        self.check_docker_access()

        container_name = self.get_container_name(repo, branch, git_repo)

        container = self.container_running(container_name)
        if container is None:
            image = self.get_image_for_repo(repo, branch, git_repo, repo_path)

            container = self.start_container(image, container_name, repo_path)

        task_filename, task_json = self.serialized_task(task)

        container.put_archive("/srv/scripts", self.tar_task_definition(task_filename, task_json))

        res = None

        try:
            command = ["timeout"]

            if self.inherit_image:
                if self.alpine_inherited or b"Alpine" in container.exec_run(["cat", "/etc/issue"], tty=True).output:
                    self.alpine_inherited = True
                    command = ["timeout", "-t"]

            command += [str(task.timeout),
                        "python",
                        "/srv/scripts/runner.py",
                        f"/srv/scripts/{task_filename}"]

            logger.debug("Running command %s", " ".join(command))

            res = container.exec_run(command, tty=True)

            # 124 is the standard, 143 on alpine
            if res.exit_code in {124, 143}:
                raise BuildTimeoutError(f"The task timeouted after {task.timeout} seconds.")

            return Result(res.output)
        except BuildError:  # can be raised by  :meth:`Result.__init__`
            raise
        except Exception as e:
            logger.exception(e)
            if res is not None:
                logger.warning(res.output)

            raise BuildError("The build failed", extra_info={
                "exception": e,
                "output": res if res is None else res.output
            })
        finally:
            if not self.keep_container_running:
                container.kill(signal.SIGKILL)
            else:
                self._containers.add(container)

    def stop_containers(self):
        """ Stops all containers used by this instance of the backend.
        """
        while len(self._containers):
            container = self._containers.pop()
            try:
                container.kill(signal.SIGKILL)
            except docker.errors.APIError:  # probably doesn't exist anymore
                pass

    def get_install_requirements_dockerfile(self, name: str, tag: str, repo_path: Path,
                                            requirements_option: RequirementsOptions) -> str:
        """
        Returns the content of a Dockerfile that will install requirements based on the repository,
        prioritizing Pipfile or Pipfile.lock and falling back on requirements.txt files
        """
        if requirements_option == RequirementsOptions.requirements_txt:
            target_file = "requirements.txt"
            requirements_files = [repo_path / self.requirements_location]

            install_cmd = "pip"
            cmd_arguments = "install -r /srv/requirements.txt"

        elif requirements_option == RequirementsOptions.pipfile:
            target_file = ""
            requirements_files = [repo_path / self.pipfile_location / "Pipfile",
                                  repo_path / self.pipfile_location / "Pipfile.lock"]

            install_cmd = "pipenv"
            cmd_arguments = "install --system --ignore-pipfile --deploy"
        else:
            raise ValueError("Invalid requirements_option")

        dockerfile = self.INSTALL_REQUIREMENTS.format(
            name=name,
            tag=tag,
            timeout=self.requirements_timeout,
            target_file=target_file,
            requirements_files=" ".join(str(x.relative_to(repo_path.parent)) for x in requirements_files),
            cmd_arguments=cmd_arguments,
            install_cmd=install_cmd
        )

        logger.debug("Installing Python requirements with Dockerfile: %s", dockerfile)

        return dockerfile
