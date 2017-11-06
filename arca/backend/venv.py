import hashlib
import json
import os
import stat
import traceback
from pathlib import Path
from typing import Tuple
from venv import EnvBuilder

import subprocess
from git import Repo

import arca
from arca.task import Task
from arca.result import Result
from arca.utils import logger
from .base import BaseBackend


class VenvBackend(BaseBackend):

    def create_or_get_venv(self, path: Path):
        requirements_file = self.get_requirements_file(path)
        if requirements_file is None:
            requirements_hash = "no_requirements_file"
        else:
            requirements_hash = hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__,
                                                   "utf-8")).hexdigest()

            logger.debug("Hashing: " + requirements_file.read_text() + arca.__version__)

        venv_path = Path(self.base_dir) / "venvs" / requirements_hash
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

                logger.debug("Return code is %s", process.returncode)
                logger.debug(out_stream.decode("utf-8"))
                logger.debug(err_stream.decode("utf-8"))

                if process.returncode:
                    venv_path.rmdir()
                    raise ValueError("Unable to install requirements.txt")  # TODO: custom exception

                logger.debug(out_stream.decode("utf-8"))
                logger.debug(err_stream.decode("utf-8"))
            else:
                logger.info("Requirements file not present in repo, empty venv it is.")
        else:
            logger.info(f"Venv already eixsts in {venv_path}")

        return venv_path

    def create_environment(self, repo: str, branch: str) -> Tuple[Repo, Path, Path]:
        git_repo, repo_path = self.get_files(repo, branch)

        venv_path = self.create_or_get_venv(repo_path)

        return git_repo, repo_path, venv_path

    def update_environment(self, repo: str, branch: str) -> Tuple[Repo, Path, Path]:
        git_repo, repo_path = self.get_files(repo, branch)

        venv_path = self.create_or_get_venv(repo_path)

        return git_repo, repo_path, venv_path

    def environment_exists(self, repo: str, branch: str):
        return self.get_path_to_repo(repo, branch).is_dir()

    def run(self, repo: str, branch: str, task: Task) -> Result:
        if self.environment_exists(repo, branch):
            git_repo, repo_path, venv_path = self.update_environment(repo, branch)
        else:
            git_repo, repo_path, venv_path = self.create_environment(repo, branch)

        script_name, script = self.create_script(task, venv_path)
        script_path = Path(self.base_dir, "scripts", script_name)
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
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       cwd=cwd)

            out_stream, err_stream = process.communicate()

            return Result(json.loads(out_stream.decode("utf-8")))
        except Exception:
            return Result({"success": False, "error": (traceback.format_exc() + "\n" +
                                                       out_stream.decode("utf-8") + "\n\n" +
                                                       err_stream.decode("utf-8"))})
