import hashlib
import json
import logging
import os
import stat
import traceback
from pathlib import Path
from typing import Tuple, Union
from venv import EnvBuilder

import subprocess
from git import Repo

import arca
from arca.task import Task
from arca.result import Result
from arca.utils import LazySettingProperty
from .base import BaseBackend


class VenvBackend(BaseBackend):

    base_dir: str = LazySettingProperty(key="base_dir", default="venv_backend")

    def get_path_to_environment_repo_base(self, repo: str) -> Path:
        return Path(self.base_dir) / self.repo_id(repo)

    def get_path_to_environment(self, repo: str, branch: str) -> Path:
        return self.get_path_to_environment_repo_base(repo).resolve() / branch

    def create_or_update_venv(self, path: Path):
        requirements_file = self.get_requirements_file(path)
        if requirements_file is None:
            requirements_hash = "no_requirements_file"
        else:
            requirements_hash = hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__,
                                                   "utf-8")).hexdigest()

            if self.verbosity > 1:
                logging.info("Hashing: " + requirements_file.read_text() + arca.__version__)

        venv_path = Path(self.base_dir) / "venvs" / requirements_hash
        if not venv_path.exists():
            if self.verbosity:
                logging.info(f"Creating a venv in {venv_path}")
            builder = EnvBuilder(with_pip=True)
            builder.create(venv_path)

            if requirements_file is not None:

                if self.verbosity:
                    if self.verbosity > 1:
                        logging.info("Requirements file:")
                        logging.info(requirements_file.read_text())
                    logging.info(f"Installing requirements from {requirements_file}")

                process = subprocess.Popen([str(venv_path / "bin" / "python3"), "-m", "pip", "install", "-r",
                                            str(requirements_file)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                [out_stream, err_stream] = process.communicate()

                if self.verbosity:
                    logging.info(f"Return code is {process.returncode}")
                    logging.info(out_stream.decode("utf-8"))
                    logging.info(err_stream.decode("utf-8"))

                if process.returncode:
                    venv_path.rmdir()
                    raise ValueError("Unable to install requirements.txt")  # TODO: custom exception

                if self.verbosity:
                    logging.info(out_stream.decode("utf-8"))
                    logging.info(err_stream.decode("utf-8"))
            else:
                if self.verbosity:
                    logging.info("Requirements file not present in repo, empty venv it is.")
        else:
            if self.verbosity:
                logging.info(f"Venv already eixsts in {venv_path}")

        return venv_path

    def create_environment(self, repo: str, branch: str, files_only: bool=False) -> Union[Tuple[Repo, Path], Repo]:
        path = self.get_path_to_environment(repo, branch)

        path.parent.mkdir(exist_ok=True, parents=True)

        if self.verbosity:
            logging.error(f"Cloning to {path}")

        # we need the specific branch and we don't actually need history -- speeds things up massively
        git_repo = Repo.clone_from(repo, str(path), branch=branch, depth=1)

        if files_only:
            return git_repo

        venv_path = self.create_or_update_venv(path)

        return git_repo, venv_path

    def update_environment(self, repo: str, branch: str, files_only: bool=False) -> Union[Tuple[Repo, Path], Repo]:
        path = self.get_path_to_environment(repo, branch)

        if self.verbosity:
            logging.error(f"Updating repo at {path}")

        git_repo = Repo.init(path)
        git_repo.remote().pull()

        if files_only:
            return git_repo

        venv_path = self.create_or_update_venv(path)

        return git_repo, venv_path

    def environment_exists(self, repo: str, branch: str):
        return self.get_path_to_environment(repo, branch).is_dir()

    def _run(self, repo: str, branch: str, task: Task) -> Result:
        if self.environment_exists(repo, branch):
            git_repo, venv_path = self.update_environment(repo, branch)
        else:
            git_repo, venv_path = self.create_environment(repo, branch)

        script = task.build_script(venv_path)
        script_hash = hashlib.md5(bytes(script, "utf-8")).hexdigest()

        script_path = Path(self.base_dir, "scripts", f"{script_hash}.py")
        script_path.parent.mkdir(parents=True, exist_ok=True)

        with script_path.open("w") as f:
            f.write(script)

        st = os.stat(str(script_path))
        script_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        out_stream = b""
        err_stream = b""

        cwd = str(self.get_path_to_environment(repo, branch) / self.cwd)

        if self.verbosity:
            logging.info("Running at cwd %s", cwd)

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

    def current_git_hash(self, repo: str, branch: str) -> str:
        if self.environment_exists(repo, branch):
            git_repo = self.update_environment(repo, branch, files_only=True)
        else:
            git_repo = self.create_environment(repo, branch, files_only=True)

        return git_repo.head.object.hexsha

    def _static_filename(self, repo: str, branch: str, relative_path: Path):
        self.validate_repo_url(repo)

        if self.environment_exists(repo, branch):
            self.update_environment(repo, branch, files_only=True)
        else:
            self.create_environment(repo, branch, files_only=True)

        path = self.get_path_to_environment(repo, branch)

        result = path / relative_path

        logging.info("Static path for %s is %s", relative_path, result)

        return result
