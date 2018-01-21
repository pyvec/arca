import hashlib
import itertools
import json
import signal
import sys
import tarfile
import time

from io import BytesIO
from pathlib import Path
from typing import Optional, List

import docker
import docker.errors
from docker.models.containers import Container
from docker.models.images import Image
from git import Repo
from requests.exceptions import ConnectionError

import arca
from arca.exceptions import ArcaMisconfigured, BuildError, PushToRegistryError
from arca.result import Result
from arca.task import Task
from arca.utils import logger, LazySettingProperty
from .base import BaseBackend


class DockerBackend(BaseBackend):

    python_version = LazySettingProperty(key="python_version", default=None)
    keep_container_running = LazySettingProperty(key="keep_container_running", default=False)
    apk_dependencies = LazySettingProperty(key="apk_dependencies", default=None)
    disable_pull = LazySettingProperty(key="disable_pull", default=False)  # so the build can be tested
    inherit_image = LazySettingProperty(key="inherit_image", default=None)
    push_to_registry_name = LazySettingProperty(key="push_to_registry_name", default=None)

    NO_REQUIREMENTS_HASH = "no_req"
    NO_DEPENDENCIES_HASH = "no_dep"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._containers = set()
        self.client = None

    def validate_settings(self):
        super().validate_settings()

        if self.inherit_image is not None and self.get_dependencies() is not None:
            raise ArcaMisconfigured("An external image is used as a base, therefore Arca can't install dependencies")

        if self.inherit_image is not None:
            try:
                assert len(str(self.inherit_image).split(":")) == 2
            except (ValueError, AssertionError):
                raise ArcaMisconfigured("Image which should be inherited is not in the proper docker format")

        if self.push_to_registry_name is not None:
            try:
                assert 2 >= len(str(self.inherit_image).split("/")) <= 3
            except ValueError:
                raise ArcaMisconfigured("Repository name where images should be pushed doesn't match the format")

    def check_docker_access(self):
        """ Checks if the current user can access docker, raises exception otherwise
        """
        try:
            if self.client is None:
                self.client = docker.from_env()
            self.client.ping()  # check that docker is running and user is permitted to access it
        except ConnectionError as e:
            logger.exception(e)
            raise BuildError("Docker is not running or the current user doesn't have permissions to access docker.")

    def get_dependencies(self) -> Optional[List[str]]:
        """ Returns a converted list of dependencies.
            Raises exception if the dependencies can't be converted into a list of strings
            Returns None if there are no dependencies.
        """

        if self.apk_dependencies is None:
            return None

        try:
            dependencies = list([str(x) for x in self.apk_dependencies])
        except (TypeError, ValueError):
            raise ArcaMisconfigured("Apk dependencies can't be converted into a list of strings")

        if not len(dependencies):
            return None
        return dependencies

    def get_python_version(self):
        """ Returns either the specified version from settings or a string of the sys.executable version
        """
        if self.python_version is None:
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        else:
            python_version = self.python_version

        return python_version

    def get_image_name(self, requirements_file: Optional[Path], dependencies: Optional[List[str]]) -> str:
        """ Returns the name of the image which are launched to run arca tasks
        """
        if self.inherit_image is None:
            return "arca_{arca_version}_{python_version}".format(
                arca_version=str(arca.__version__),
                python_version=self.get_python_version()
            )
        else:
            name, tag = str(self.inherit_image).split(":")

            return f"arca_{name}_{tag}"

    def get_dependencies_hash(self, dependencies):
        return hashlib.sha1(bytes(",".join(dependencies), "utf-8")).hexdigest()

    def get_image_tag(self, requirements_file: Optional[Path], dependencies: Optional[List[str]]) -> str:
        """ Returns the tag for images with proper requirements and dependencies installed
            Possible outputs:
                - `no_req` - if inheriting from a specified image
                - `<requirements_hash>` - if inheriting from a specified image
                - `no_dep_no_req`
                - `<dependencies_hash>_no_req`
                - `no_dep_<requirements_hash>`
                - `<dependencies_hash>_<requirements_hash>`
        """
        if requirements_file is None:
            requirements_hash = self.NO_REQUIREMENTS_HASH
        else:
            requirements_hash = self.get_requirements_hash(requirements_file)

        if self.inherit_image is None:
            if dependencies is None:
                dependencies_hash = self.NO_DEPENDENCIES_HASH
            else:
                dependencies_hash = self.get_dependencies_hash(dependencies)

            if dependencies is not None and requirements_file is not None:
                return f"{dependencies_hash[:25]}_{requirements_hash[:25]}"

            return f"{dependencies_hash}_{requirements_hash}"
        else:
            return requirements_hash

    def get_arca_base_name(self):
        return "docker.io/mikicz/arca"

    def get_python_base_tag(self, python_version):
        return f"{arca.__version__}_{python_version}"

    def get_or_build_image(self, name, tag, dockerfile, pull=True, build_context: Optional[Path]= None):
        """ A proxy for commonly built images, returns them from the local system if they exist, tries to pull them if
            pull isn't disabled, otherwise builds them by the definition in `dockerfile`. `dockerfile` can be callable.
        """
        if self.image_exists(name, tag):
            logger.info("Image %s:%s exists", name, tag)
            return name, tag

        elif pull:
            logger.info("Trying to pull image %s:%s", name, tag)

            try:
                self.client.images.pull(name, tag=tag)
                logger.info("The image %s:%s was pulled from repository", name, tag)
                return name, tag
            except docker.errors.APIError:
                logger.info("The image %s:%s can't be pulled, building locally.", name, tag)

        if callable(dockerfile):
            dockerfile = dockerfile()

        try:
            if build_context is None:
                self.client.images.build(
                    fileobj=dockerfile,
                    pull=True,
                    tag=f"{name}:{tag}"
                )
            else:
                dockerfile_file = build_context / "dockerfile"
                dockerfile_file.write_bytes(dockerfile.getvalue())

                self.client.images.build(
                    path=str(build_context.resolve()),
                    pull=pull,
                    dockerfile=dockerfile_file.name,
                    tag=f"{name}:{tag}"
                )

                dockerfile_file.unlink()
        except docker.errors.BuildError as e:
            logger.exception(e)
            raise

        return name, tag

    def get_arca_base(self, pull=True):
        """ Returns the name and tag of image that has the basic build dependencies installed with just pyenv installed,
            with no python installed.
        """
        name = self.get_arca_base_name()
        tag = arca.__version__

        pyenv_installer = "https://raw.githubusercontent.com/pyenv/pyenv-installer/master/bin/pyenv-installer"
        dockerfile = BytesIO(bytes(f"""
            FROM alpine:3.5
            RUN apk add --no-cache curl bash git nano g++ make jpeg-dev zlib-dev ca-certificates openssl-dev \
                                   readline-dev bzip2-dev sqlite-dev ncurses-dev linux-headers build-base \
                                   openssh

            RUN curl -L {pyenv_installer} -o /pyenv-installer && \
                  touch /root/.bashrc && \
                  /bin/ln -s /root/.bashrc /root/.bash_profile && \
                  /bin/bash /pyenv-installer && \
                  rm /pyenv-installer && \
                  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bash_profile && \
                  echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bash_profile && \
                  echo 'eval "$(pyenv init -)"' >> ~/.bash_profile

            ENV HOME  /root
            ENV PYENV_ROOT $HOME/.pyenv
            ENV PATH $PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

            SHELL ["bash", "-lc"]
            CMD bash -i
            """, encoding="utf-8"))

        return self.get_or_build_image(name, tag, dockerfile, pull=pull)

    def get_python_base(self, python_version, pull=True):
        """ Returns the name and tag of an image with specified `python_version` installed.
        """
        name = self.get_arca_base_name()
        tag = self.get_python_base_tag(python_version)

        def get_dockerfile():
            base_arca_name, base_arca_tag = self.get_arca_base(pull)

            return BytesIO(bytes(f"""
                FROM {base_arca_name}:{base_arca_tag}
                RUN pyenv update
                RUN pyenv install {python_version}
                ENV PYENV_VERSION {python_version}
                RUN mkdir /srv/scripts
                CMD bash -i
                """, encoding="utf-8"))

        return self.get_or_build_image(name, tag, get_dockerfile, pull=pull)

    def pull_or_get(self, name, tag):
        if self.image_exists(name, tag):
            return name, tag
        try:
            self.client.images.pull(name, tag)
        except docker.errors.APIError:
            raise ArcaMisconfigured("The specified image from which Arca should inherit can't be pulled")
        return name, tag

    def create_image(self, image_name: str, image_tag: str,
                     build_context: Path,
                     requirements_file: Optional[Path],
                     dependencies: Optional[List[str]]) -> Image:
        """ Builds an image for specific requirements and dependencies.
        """
        python_version = self.get_python_version()

        if requirements_file is None:  # requirements file doesn't exist in the repo
            if self.inherit_image is None:
                base_name, base_tag = self.get_python_base(python_version, pull=not self.disable_pull)
            else:
                base_name, base_tag = str(self.inherit_image).split(":")
                self.pull_or_get(base_name, base_tag)

            # no requirements and no dependencies, just return the basic image with the correct python installed
            if dependencies is None:
                image = self.get_image(base_name, base_tag)
                image.tag(image_name, image_tag)  # so `create_image` doesn't have to be called next time

                return image

            serialized_dependencies = " ".join(dependencies)

            # extend the image with correct python by installing the dependencies
            install_dependencies = BytesIO(bytes(f"""
                FROM {base_name}:{base_tag}
                RUN apk update
                RUN apk add --no-cache {serialized_dependencies}
                CMD bash -i
            """, encoding="utf-8"))

            self.get_or_build_image(image_name, image_tag, install_dependencies)

            return self.get_image(image_name, image_tag)

        def get_installed_dependencies():
            """ Returns the image_name and image_tag for either an image with all the dependencies installed
                or just an image with python installed if there aren't any dependencies.
            """
            if dependencies is not None:
                def install_dependencies():
                    python_name, python_tag = self.get_python_base(python_version, pull=not self.disable_pull)
                    dependencies_serialized = " ".join(self.get_dependencies())

                    return BytesIO(bytes(f"""
                        FROM {python_name}:{python_tag}
                        RUN apk update
                        RUN apk add --no-cache {dependencies_serialized}
                        CMD bash -i
                    """, encoding="utf-8"))

                return self.get_or_build_image(image_name, self.get_image_tag(None, dependencies),
                                               install_dependencies, pull=not self.disable_pull)
            else:
                if self.inherit_image is None:
                    return self.get_python_base(python_version, pull=not self.disable_pull)
                else:
                    name, tag = self.inherit_image.split(":")
                    self.pull_or_get(name, tag)
                    return name, tag

        def install_requirements():
            for_req_name, for_req_tag = get_installed_dependencies()

            requirements_file_relative = requirements_file.relative_to(build_context)

            return BytesIO(bytes(f"""
                FROM {for_req_name}:{for_req_tag}
                ADD {requirements_file_relative} /srv/requirements.txt
                RUN pip install -r /srv/requirements.txt
                CMD bash -i
            """, encoding="utf-8"))

        self.get_or_build_image(image_name, image_tag, install_requirements, build_context=build_context,
                                pull=False)

        return self.get_image(image_name, image_tag)

    def push_to_registry(self, image: Image, image_tag: str):
        image.tag(self.push_to_registry_name, image_tag)

        result = self.client.images.push(self.push_to_registry_name, image_tag)

        result = result.strip()  # remove empty line at the end of output

        # the last can have one of two outputs, either
        # {"progressDetail":{},"aux":{"Tag":"<tag>","Digest":"sha256:<hash>","Size":<size>}}
        # when the push is successful, or
        # {"errorDetail": {"message":"<error_msg>"},"error":"<error_msg>"}
        # when the push is not successful

        last_line = json.loads(result.split("\n")[-1])

        if "error" in last_line:
            raise PushToRegistryError(f"Push of the image failed because of: {last_line['error']}", full_output=result)

        logger.info("Pushed image to registry %s:%s", self.push_to_registry_name, image_tag)
        logger.debug("Info:\n%s", result)

    def image_exists(self, image_name, image_tag):
        # TODO: Is there a better filter?
        return f"{image_name}:{image_tag}" in itertools.chain(*[image.tags for image in self.client.images.list()])

    def get_image(self, image_name, image_tag) -> Image:
        return self.client.images.get(f"{image_name}:{image_tag}")

    def try_pull_image_from_registry(self, image_name, image_tag) -> Optional[Image]:
        try:
            image: Image = self.client.images.pull(self.push_to_registry_name, image_tag)
        except (docker.errors.ImageNotFound, docker.errors.NotFound):  # the image doesn't exist
            logger.info("Tried to pull %s:%s from a registry, not found", self.push_to_registry_name, image_tag)
            return None

        logger.info("Pulled %s:%s from registry, tagged %s:%s", self.push_to_registry_name, image_tag,
                    image_name, image_tag)

        # the name and tag are different on the repo, let's tag it with local name so exists checks run smoothly
        image.tag(image_name, image_tag)

        return image

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> Image:
        """ Returns an image for the specific repo (based on its requirements)
        """
        requirements_file = self.get_requirements_file(repo_path)
        dependencies = self.get_dependencies()

        image_name = self.get_image_name(requirements_file, dependencies)
        image_tag = self.get_image_tag(requirements_file, dependencies)

        if self.image_exists(image_name, image_tag):
            return self.get_image(image_name, image_tag)

        if self.push_to_registry_name is not None:
            # the target image might have been built and pushed in a previous run already, let's try to pull it
            img = self.try_pull_image_from_registry(image_name, image_tag)

            if img is not None:  # image wasn't found
                return img

        image = self.create_image(image_name, image_tag, repo_path.parent, requirements_file, dependencies)

        if self.push_to_registry_name is not None:
            self.push_to_registry(image, image_tag)

        return image

    def container_running(self, container_name) -> Optional[Container]:
        """ Finds out if a container with name `container_name` is running, returns it if it does, None otherwise.
        """
        filters = {
            "name": container_name,
            "status": "running",
        }

        for container in self.client.containers.list(filters=filters):
            if container_name == container.name:
                return container
        return None

    def tar_files(self, path: Path):
        """ Creates a tar with the git repository
        """
        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')
        tar.add(path, arcname="data", recursive=True)
        tar.close()
        return tarstream.getvalue()

    def start_container(self, image, container_name, repo_path: Path) -> Container:
        """ Starts a container with image `image` and name `container_name` and copies the git into the container.
        """
        container = self.client.containers.run(image, command="bash -i", detach=True, tty=True, name=container_name,
                                               working_dir=str((Path("/srv/data") / self.cwd).resolve()),
                                               auto_remove=True)

        container.exec_run(["mkdir", "-p", "/srv"])
        container.put_archive("/srv", self.tar_files(repo_path))

        return container

    def tar_script(self, name, script):
        """ Creates a tar with the script to lunch
        """
        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')
        tarinfo = tarfile.TarInfo(name=name)

        tarinfo.size = len(script)
        tarinfo.mtime = time.time()
        tar.addfile(tarinfo, BytesIO(script.encode("utf-8")))
        tar.close()

        return tarstream.getvalue()

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:
        """ Gets or builds an image for the repo, gets or starts a container for the image and runs the scripts.
        """
        self.check_docker_access()

        image = self.get_or_create_environment(repo, branch, git_repo, repo_path)

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )

        container = self.container_running(container_name)
        if container is None:
            container = self.start_container(image, container_name, repo_path)

        script_name, script = self.create_script(task)

        container.exec_run(["mkdir", "-p", "/srv/scripts"])
        container.put_archive("/srv/scripts", self.tar_script(script_name, script))

        try:
            res = container.exec_run(["python", f"/srv/scripts/{script_name}"], tty=True)

            return Result(json.loads(res))
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e
            })
        finally:
            if not self.keep_container_running:
                container.kill(signal.SIGKILL)
            else:
                self._containers.add(container)

    def stop_containers(self):
        """ Stops all containers used by this instance of the backend
        """
        while len(self._containers):
            container = self._containers.pop()
            try:
                container.kill(signal.SIGKILL)
            except docker.errors.APIError:  # probably doesn't exist anymore
                pass
