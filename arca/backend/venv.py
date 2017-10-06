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
from .base import BaseBackend


class VenvBackend(BaseBackend):

    def __init__(self, *, base_dir="venv_backend", **kwargs):
        super().__init__(**kwargs)
        self.base_dir = base_dir

    def get_path_to_environment_repo_base(self, repo: str) -> Path:
        return Path(self.base_dir) / self.repo_id(repo)

    def get_path_to_environment(self, repo: str, branch: str) -> Path:
        return (self.get_path_to_environment_repo_base(repo) / branch).resolve()

    def create_or_update_venv(self, path: Path):
        requirements_file = self.get_requirements_file(path)
        if requirements_file is None:
            requirements_hash = "no_requirements_file"
        else:
            requirements_hash = hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__,
                                                   "utf-8")).hexdigest()

            if self.verbosity > 1:
                print("Hashing: " + requirements_file.read_text() + arca.__version__)

        venv_path = Path(self.base_dir) / "venvs" / requirements_hash
        if not venv_path.exists():
            if self.verbosity:
                print(f"Creating a venv in {venv_path}")
            builder = EnvBuilder(with_pip=True)
            builder.create(venv_path)

            if requirements_file is not None:

                if self.verbosity:
                    if self.verbosity > 1:
                        print("Requirements file:")
                        print(requirements_file.read_text())
                    print(f"Installing requirements from {requirements_file}")

                old_userbase = os.environ.get("PYTHONUSERBASE", None)

                os.environ["PYTHONUSERBASE"] = str(venv_path)

                pip_install_command = [str(venv_path / "bin" / "python3"), "-m", "pip", "install", "-vv", "--user",
                                       "-r", str(requirements_file)]

                if old_userbase is None:
                    del os.environ["PYTHONUSERBASE"]
                else:
                    os.environ["PYTHONUSERBASE"] = old_userbase

                if self.verbosity > 1:
                    print(" ".join(pip_install_command))

                process = subprocess.Popen(pip_install_command,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                [out_stream, err_stream] = process.communicate()

                if self.verbosity:
                    print(f"Return code is {process.returncode}")
                    print(out_stream.decode("utf-8"))
                    print(err_stream.decode("utf-8"))

                if process.returncode:
                    venv_path.rmdir()
                    raise ValueError("Unable to install requirements.txt")  # TODO: custom exception

                if self.verbosity:
                    print(out_stream.decode("utf-8"))
                    print(err_stream.decode("utf-8"))
            else:
                if self.verbosity:
                    print("Requirements file not present in repo, empty venv it is.")
        else:
            if self.verbosity:
                print(f"Venv already eixsts in {venv_path}")

        return venv_path

    def create_environment(self, repo: str, branch: str) -> Tuple[Repo, Path]:
        clone_from_local_subdirectory: Repo = None
        repo_base = self.get_path_to_environment_repo_base(repo)
        path = self.get_path_to_environment(repo, branch)

        if repo_base.exists() and not repo.startswith("file://"):
            subdirectories = [x for x in repo_base.iterdir() if (x.is_dir() and x.name != branch)]
            if len(subdirectories) > 0:
                clone_from_local_subdirectory = Repo.init(subdirectories[0])

        if clone_from_local_subdirectory is not None:
            if self.verbosity:
                print(f"Cloning from a local subdirectory {clone_from_local_subdirectory}")

            git_repo = clone_from_local_subdirectory.clone(path)
            git_repo.remote().set_url(repo)
            git_repo.remote().pull()
        else:
            git_repo = Repo.clone_from(repo, str(path))

        git_repo.git.checkout(branch)

        venv_path = self.create_or_update_venv(path)

        return git_repo, venv_path

    def update_environment(self, repo: str, branch: str) -> Tuple[Repo, Path]:
        path = self.get_path_to_environment(repo, branch)
        git_repo = Repo.init(path)
        git_repo.remote().pull()

        venv_path = self.create_or_update_venv(path)

        return git_repo, venv_path

    def environment_exists(self, repo: str, branch: str):
        return self.get_path_to_environment(repo, branch).is_dir()

    def run(self, repo: str, branch: str, task: Task) -> Result:
        self.validate_repo_url(repo)

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

        try:
            process = subprocess.Popen([str(venv_path / "bin" / "python3"), str(script_path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       cwd=str(self.get_path_to_environment(repo, branch) / self.cwd))

            out_stream, _ = process.communicate()

            return Result(json.loads(out_stream))
        except:
            return Result({"success": False, "error": traceback.format_exc()})
