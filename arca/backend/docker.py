import itertools
import json
import sys
import tarfile
import time

from io import BytesIO
from pathlib import Path
from typing import Optional

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
    disable_pull = LazySettingProperty(key="disable_pull", default=False)  # so the build can be tested

    def __init__(self, **kwargs):
        super(DockerBackend, self).__init__(**kwargs)

        self._containers = set()

        try:
            self.client = docker.from_env()
            self.client.ping()  # check that docker is running and user is permitted to access it
        except ConnectionError:
            # TODO: Custom exception
            raise ValueError("Docker is not running or the current user doesn't have permissions to access docker.")

    def get_python_version(self):
        if self.python_version is None:
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        else:
            python_version = self.python_version

        return python_version

    def get_image_name(self, repo: str, branch: str) -> str:
        return "arca_{python_version}_{arca_version}_{repo_id}_{branch}".format(
            arca_version=str(arca.__version__),
            python_version=self.get_python_version(),
            repo_id=self._arca.repo_id(repo),
            branch=branch
        )

    def get_image_tag(self, repo: str, branch: str) -> str:
        return self.current_git_hash(repo, branch, short=True)

    def get_docker_base_name(self):
        return "docker.io/mikicz/arca"

    def get_docker_base_tag(self, python_version):
        return f"{arca.__version__}_{python_version}"

    def get_or_build_image(self, name, tag, dockerfile, pull=True):
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
            self.client.images.build(
                fileobj=dockerfile,
                pull=True,
                tag=f"{name}:{tag}"
            )
        except BuildError as e:
            logger.exception(e)
            raise

        return name, tag

    def get_arca_base(self, pull=True):
        name = self.get_docker_base_name()
        tag = arca.__version__

        pyenv_installer = "https://raw.githubusercontent.com/pyenv/pyenv-installer/master/bin/pyenv-installer"
        dockerfile = BytesIO(bytes(f"""
            FROM alpine:3.5
            RUN apk add --no-cache curl bash git nano g++ make jpeg-dev zlib-dev ca-certificates openssl-dev \
                                   readline-dev bzip2-dev sqlite-dev ncurses-dev linux-headers build-base

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
        name = self.get_docker_base_name()
        tag = self.get_docker_base_tag(python_version)

        def get_dockerfile():
            base_arca_name, base_arca_tag = self.get_arca_base(pull)

            return BytesIO(bytes(f"""
                FROM {base_arca_name}:{base_arca_tag}
                RUN pyenv update
                RUN pyenv install {python_version}
                ENV PYENV_VERSION {python_version}
                CMD bash -i
                """, encoding="utf-8"))

        return self.get_or_build_image(name, tag, get_dockerfile, pull=pull)

    def create_image(self, repo: str, branch: str, image_name: str, image_tag: str):
        python_version = self.get_python_version()

        base_name, base_tag = self.get_python_base(python_version, pull=not self.disable_pull)

        git_repo, repo_path = self.get_files(repo, branch)

        requirements_file = self.get_requirements_file(repo_path)
        if requirements_file is not None:
            requirements_file = "RUN pip install -r {}".format(
                Path("/srv/data") / self.requirements_location
            )
        else:
            requirements_file = ""

        workdir = Path("/srv/data") / self.cwd

        dockerfile_path = repo_path.parent / f"docker_{branch}"
        dockerfile_path.write_text(f"""
            FROM {base_name}:{base_tag}
            RUN mkdir /srv/scripts/
            COPY {branch} /srv/data/
            {requirements_file}

            WORKDIR {workdir.resolve()}

            CMD bash -i
        """)

        logger.info("Started building %s:%s", image_name, image_tag)
        try:
            image = self.client.images.build(
                path=str(repo_path.parent.resolve()),
                tag=f"{image_name}:{image_tag}",
                dockerfile=f"docker_{branch}"
            )
        except BuildError as e:
            logger.exception(e)
            raise

        logger.info("Finished building %s:%s", image_name, image_tag)

        return image

    def image_exists(self, image_name, image_tag):
        return f"{image_name}:{image_tag}" in itertools.chain(*[image.tags
                                                                for image in self.client.images.list()])

    def get_or_create_environment(self, repo: str, branch: str) -> Image:
        image_name = self.get_image_name(repo, branch)
        image_tag = self.get_image_tag(repo, branch)

        if self.image_exists(image_name, image_tag):
            return self.client.images.get(f"{image_name}:{image_tag}")

        return self.create_image(repo, branch, image_name, image_tag)

    def container_running(self, image) -> Optional[Container]:
        for container in self.client.containers.list():
            if image == container.image:
                return container
        return None

    def start_container(self, image) -> Container:
        return self.client.containers.run(image, command="bash -i", detach=True, tty=True)

    def tar_file(self, name, script):
        tarstream = BytesIO()
        tar = tarfile.TarFile(fileobj=tarstream, mode='w')
        tarinfo = tarfile.TarInfo(name=name)

        tarinfo.size = len(script)
        tarinfo.mtime = time.time()
        tar.addfile(tarinfo, BytesIO(script.encode("utf-8")))
        tar.close()

        return tarstream.getvalue()

    def run(self, repo: str, branch: str, task: Task) -> Result:
        image = self.get_or_create_environment(repo, branch)

        container = self.container_running(image)
        if container is None:
            container = self.start_container(image)

        script_name, script = self.create_script(task)

        container.exec_run(["mkdir", "-p", "/srv/scripts"])
        container.put_archive("/srv/scripts", self.tar_file(script_name, script))

        try:
            res = container.exec_run(["python", f"/srv/scripts/{script_name}"], tty=True)

            return Result(json.loads(res))
        except Exception as e:
            logger.exception(e)
            return Result({"success": False, "error": str(e)})
        finally:
            if not self.keep_container_running:
                container.kill("9")
            else:
                self._containers.add(container)

    def stop_containers(self):
        while len(self._containers):
            container = self._containers.pop()
            try:
                container.kill("9")
            except APIError:  # probably doesn't exist anymore
                pass
