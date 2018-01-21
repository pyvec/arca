import json
import os
import stat
from pathlib import Path
from venv import EnvBuilder

import subprocess
from git import Repo

import arca
from arca.task import Task
from arca.result import Result
from arca.utils import logger
from arca.exceptions import BuildError
from .base import BaseBackend


class VenvBackend(BaseBackend):

    def create_or_get_venv(self, path: Path):
        requirements_file = self.get_requirements_file(path)
        if requirements_file is None:
            requirements_hash = "no_requirements_file"
        else:
            requirements_hash = self.get_requirements_hash(requirements_file)

            logger.debug("Hashing: " + requirements_file.read_text() + arca.__version__)

        venv_path = Path(self._arca.base_dir) / "venvs" / requirements_hash

        if not venv_path.exists():
            logger.info(f"Creating a venv in {venv_path}")
            builder = EnvBuilder(with_pip=True)
            builder.create(venv_path)

            if requirements_file is not None:

                logger.debug("Requirements file:")
                logger.debug(requirements_file.read_text())
                logger.info("Installing requirements from %s", requirements_file)

                process = subprocess.Popen([str(venv_path / "bin" / "python3"), "-m", "pip", "install", "-r",
                                            str(requirements_file)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                [out_stream, err_stream] = process.communicate()
                out_stream = out_stream.decode("utf-8")
                err_stream = err_stream.decode("utf-8")

                logger.debug("Return code is %s", process.returncode)
                logger.debug(out_stream)
                logger.debug(err_stream)

                if process.returncode:
                    venv_path.rmdir()
                    raise BuildError("Unable to install requirements.txt", extra_info={
                        "out_stream": out_stream,
                        "err_stream": err_stream,
                        "returncode": process.returncode
                    })

            else:
                logger.info("Requirements file not present in repo, empty venv it is.")
        else:
            logger.info(f"Venv already eixsts in {venv_path}")

        return venv_path

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> Path:
        return self.create_or_get_venv(repo_path)

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:
        venv_path = self.get_or_create_environment(repo, branch, git_repo, repo_path)

        script_name, script = self.create_script(task, venv_path)
        script_path = Path(self._arca.base_dir, "scripts", script_name)
        script_path.parent.mkdir(parents=True, exist_ok=True)

        with script_path.open("w") as f:
            f.write(script)

        st = os.stat(str(script_path))
        script_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        out_stream = b""
        err_stream = b""

        cwd = str(repo_path / self.cwd)

        logger.info("Running at cwd %s", cwd)

        try:
            process = subprocess.Popen([str(venv_path.resolve() / "bin" / "python"), str(script_path.resolve())],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       cwd=cwd)

            out_stream, err_stream = process.communicate()

            return Result(json.loads(out_stream.decode("utf-8")))
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e,
                "out_stream": out_stream,
                "err_stream": err_stream,
            })
