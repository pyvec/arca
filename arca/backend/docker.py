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
from docker.errors import BuildError, APIError
from docker.models.containers import Container
from docker.models.images import Image
from requests.exceptions import ConnectionError

import arca
from arca.result import Result
from arca.task import Task
from arca.utils import logger, LazySettingProperty
from .base import BaseBackend


class DockerBackend(BaseBackend):

    python_version = LazySettingProperty(key="python_version", default=None)
    keep_container_running = LazySettingProperty(key="keep_container_running", default=False)
    apk_dependencies = LazySettingProperty(key="apk_dependencies", default=None)
    disable_pull = LazySettingProperty(key="disable_pull", default=False)  # so the build can be tested

    NO_REQUIREMENTS_HASH = "no_req"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._containers = set()
        self.client = None

    def check_docker_access(self):
        """ Checks if the current user can access docker, raises exception otherwise
        """
        try:
            if self.client is None:
                self.client = docker.from_env()
            self.client.ping()  # check that docker is running and user is permitted to access it
        except ConnectionError as e:
            logger.exception(e)
            # TODO: Custom exception
            raise ValueError("Docker is not running or the current user doesn't have permissions to access docker.")

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
            # TODO: Custom exception
            raise ValueError("Apk dependencies can't be converted into a list of strings")

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
        return "arca_{arca_version}_{python_version}".format(
            arca_version=str(arca.__version__),
            python_version=self.get_python_version()
        )

    def get_image_tag(self, requirements_file: Optional[Path], dependencies: Optional[List[str]]) -> str:
        """ Returns the tag for images with proper requirements and dependencies installed
            Possible outputs:
                - `no_req`
                - `no_req_<dependencies_hash>`
                - `<requirements_hash>`
                - `<requirements_hash>_<dependencies_hash>`
        """

        if requirements_file is None:
            requirements_hash = self.NO_REQUIREMENTS_HASH
        else:
            requirements_hash = self.get_requirements_hash(requirements_file)

        if dependencies is not None:
            return "{}_{}".format(
                requirements_hash,
                hashlib.sha256(bytes(",".join(dependencies), "utf-8")).hexdigest()
            )
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
            except APIError:
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
        except BuildError as e:
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

    def create_image(self, image_name: str, image_tag: str,
                     build_context: Path,
                     requirements_file: Optional[Path],
                     dependencies: Optional[List[str]]) -> Image:
        """ Builds an image for specific requirements and dependencies.
        """
        python_version = self.get_python_version()

        if requirements_file is None:  # requirements file doesn't exist in the repo
            base_name, base_tag = self.get_python_base(python_version, pull=not self.disable_pull)
            image = self.get_image(base_name, base_tag)
            image.tag(image_name, image_tag)  # so `create_image` doesn't have to be called next time

            # no requirements and no dependencies, just return the basic image with the correct python installed
            if image_tag == self.NO_REQUIREMENTS_HASH:
                return image

            serialized_dependencies = " ".join(dependencies)

            # extend the image with corrent python by installing the dependencies
            install_dependencies = BytesIO(bytes(f"""
                FROM {image_name}:{self.NO_REQUIREMENTS_HASH}
                RUN apk add --no-cache {serialized_dependencies}
                CMD bash -i
            """, encoding="utf-8"))

            self.get_or_build_image(image_name, image_tag, install_dependencies)

            return self.get_image(image_name, image_tag)

        # there are some requirements
        requirements_hash = self.get_requirements_hash(requirements_file)

        def install_requirements():
            python_name, python_tag = self.get_python_base(python_version, pull=not self.disable_pull)

            requirements_file_relative = requirements_file.relative_to(build_context)

            return BytesIO(bytes(f"""
                FROM {python_name}:{python_tag}
                ADD {requirements_file_relative} /srv/requirements.txt
                RUN pip install -r /srv/requirements.txt
                CMD bash -i
            """, encoding="utf-8"))

        self.get_or_build_image(image_name, requirements_hash, install_requirements, build_context=build_context)

        if image_tag == requirements_hash:
            return self.get_image(image_name, image_tag)

        dependencies = " ".join(self.get_dependencies())

        install_dependencies = BytesIO(bytes(f"""
            FROM {image_name}:{requirements_hash}
            RUN apk add --no-cache {dependencies}
            CMD bash -i
        """, encoding="utf-8"))

        self.get_or_build_image(image_name, image_tag, install_dependencies)

        return self.get_image(image_name, image_tag)

    def image_exists(self, image_name, image_tag):
        # TODO: Is there a better filter?
        return f"{image_name}:{image_tag}" in itertools.chain(*[image.tags for image in self.client.images.list()])

    def get_image(self, image_name, image_tag) -> Image:
        return self.client.images.get(f"{image_name}:{image_tag}")

    def get_or_create_environment(self, repo: str, branch: str) -> Image:
        """ Returns an image for the specific repo (based on its requirements)
        """
        _, path = self.get_files(repo, branch)
        requirements_file = self.get_requirements_file(path)
        dependencies = self.get_dependencies()

        image_name = self.get_image_name(requirements_file, dependencies)
        image_tag = self.get_image_tag(requirements_file, dependencies)

        if self.image_exists(image_name, image_tag):
            return self.get_image(image_name, image_tag)

        return self.create_image(image_name, image_tag, path.parent, requirements_file, dependencies)

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

    def start_container(self, image, container_name, repo, branch) -> Container:
        """ Starts a container with image `image` and name `container_name` and copies the git into the container.
        """

        container = self.client.containers.run(image, command="bash -i", detach=True, tty=True, name=container_name,
                                               working_dir=str((Path("/srv/data") / self.cwd).resolve()),
                                               auto_remove=True)

        _, path = self.get_files(repo, branch)

        container.exec_run(["mkdir", "-p", "/srv"])
        container.put_archive("/srv", self.tar_files(path))

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

    def run(self, repo: str, branch: str, task: Task) -> Result:
        """ Gets or builds an image for the repo, gets or starts a container for the image and runs the scripts.
        """
        self.check_docker_access()

        image = self.get_or_create_environment(repo, branch)

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self.current_git_hash(repo,  branch, short=True)
        )

        container = self.container_running(container_name)
        if container is None:
            container = self.start_container(image, container_name, repo, branch)

        script_name, script = self.create_script(task)

        container.exec_run(["mkdir", "-p", "/srv/scripts"])
        container.put_archive("/srv/scripts", self.tar_script(script_name, script))

        try:
            res = container.exec_run(["python", f"/srv/scripts/{script_name}"], tty=True)

            return Result(json.loads(res))
        except Exception as e:
            logger.exception(e)
            return Result({"success": False, "error": str(e)})
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
            except APIError:  # probably doesn't exist anymore
                pass
