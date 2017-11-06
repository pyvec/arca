import itertools
import json
import sys
import tarfile
import time

from io import BytesIO
from pathlib import Path

import docker
from docker.errors import BuildError
from docker.models.containers import Container
from requests.exceptions import ConnectionError

import arca
from arca.result import Result
from arca.task import Task
from arca.utils import logger, LazySettingProperty
from .base import BaseBackend


class DockerBackend(BaseBackend):

    python_version = LazySettingProperty(key="python_version", default=None)

    def __init__(self, **kwargs):
        super(DockerBackend, self).__init__(**kwargs)

        try:
            self.client = docker.from_env()
            self.client.ping()  # check that docker is running and user is permitted to access it
        except ConnectionError:
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

    def get_docker_base(self, python_version):
        name = "arca_{python_version}".format(
            python_version=python_version
        )
        tag = str(arca.__version__)

        if self.image_exists(name, tag):
            logger.info("Docker base %s:%s does exist", name, tag)
            return name, tag

        logger.info("Docker base %s:%s doesn't exist, building", name, tag)

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
            RUN pyenv update
            RUN pyenv install {python_version}

            ENV PYENV_VERSION {python_version}
            CMD bash -i
            """, encoding="utf-8"))

        try:
            self.client.images.build(
                fileobj=dockerfile,
                pull=True,
                tag=f"{name}:{tag}"
            )
        except BuildError as e:
            logger.exception(e)
            raise

        logger.info("Docker base %s:%s created", name, tag)

        return name, tag

    def create_environment(self, repo: str, branch: str):
        python_version = self.get_python_version()

        base_name, base_tag = self.get_docker_base(python_version)

        image_name = self.get_image_name(repo, branch)
        image_tag = self.get_image_tag(repo, branch)
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

    def update_environment(self, repo: str, branch: str):
        image_name = self.get_image_name(repo, branch)
        image_tag = self.get_image_tag(repo, branch)
        return self.client.images.get(f"{image_name}:{image_tag}")

    def image_exists(self, image_name, image_tag):
        return f"{image_name}:{image_tag}" in itertools.chain(*[image.tags
                                                                for image in self.client.images.list()])

    def environment_exists(self, repo: str, branch: str):
        image_name = self.get_image_name(repo, branch)
        image_tag = self.get_image_tag(repo, branch)

        return self.image_exists(image_name, image_tag)

    def container_running(self, image):
        for container in self.client.containers.list():
            if image == container.image:
                return container
        return None

    def start_container(self, image):
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
        if not self.environment_exists(repo, branch):
            image = self.create_environment(repo, branch)
        else:
            image = self.update_environment(repo, branch)

        container: Container = self.container_running(image)
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
            container.kill("9")
