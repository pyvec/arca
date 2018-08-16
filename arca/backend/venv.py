import shlex
import shutil
import subprocess
from pathlib import Path
from venv import EnvBuilder

from git import Repo

from arca.exceptions import BuildError, BuildTimeoutError
from arca.utils import logger
from .base import BaseRunInSubprocessBackend


class VenvBackend(BaseRunInSubprocessBackend):
    """
    Uses Python virtual environments (see :mod:`venv`), the tasks are then launched in a :mod:`subprocess`.
    The virtual environments are shared across repositories when they have the exact same requirements.
    If the target repository doesn't have requirements, it also uses a virtual environment, but just with
    no extra packages installed.

    There are no extra settings for this backend.
    """

    def get_virtualenv_path(self, path: Path) -> Path:
        """
        Returns the path to the virtualenv the current state of the repository.

        Either:

        * hash of Pipfile.lock and Arca's version
        * hash of Pipfile and Arca's version
        * hash of the requirements file and Arca's version
        * ``no_requirements`` if the requirements file doesn't exist.

        :param Path: :class:`Path <pathlib.Path>` to where the repository

        """
        pipfiles = self.get_pipfiles(path)

        logger.debug("Pipfiles: %s", pipfiles)

        if pipfiles is not None:
            venv_name = self.get_pipfile_hash(*pipfiles)
        else:
            requirements_file = self.get_requirements_file(path)

            logger.debug("Requirement file: %s", requirements_file)

            if requirements_file is not None:
                venv_name = self.get_requirements_hash(requirements_file)
            else:
                logger.debug("No pipfile or requirement file")

                venv_name = "no_requirements"

        return Path(self._arca.base_dir) / "venvs" / venv_name

    def get_or_create_venv(self, path: Path) -> Path:
        """
        Gets the location of  the virtualenv from :meth:`get_virtualenv_path`, checks if it exists already,
        creates it and installs requirements otherwise. The virtualenvs are stored in a folder based
        on the :class:`Arca` ``base_dir`` setting.

        :param path: :class:`Path <pathlib.Path>` to the cloned repository.
        """
        venv_path = self.get_virtualenv_path(path)

        if not venv_path.exists():
            logger.info(f"Creating a venv in {venv_path}")
            builder = EnvBuilder(with_pip=True)
            builder.create(venv_path)

            pipfiles = self.get_pipfiles(path)

            shell = False
            cmd = None
            cwd = None

            if pipfiles is not None:
                pipfile, lock = pipfiles

                cmd = ["source", (str(venv_path / "bin" / "activate")), "&&", "pipenv"]

                if lock is not None:
                    cmd += ["install", "--ignore-pipfile"]
                else:
                    cmd += ["install", "--skip-lock"]

                cmd = " ".join(cmd)

                cwd = path / self.pipfile_location
                shell = True
            else:
                requirements_file = self.get_requirements_file(path)

                if requirements_file is not None:
                    logger.debug("Requirements file:")
                    logger.debug(requirements_file.read_text())
                    logger.info("Installing requirements from %s", requirements_file)

                    cmd = [str(venv_path / "bin" / "python3"), "-m", "pip", "install", "-r",
                           shlex.quote(str(requirements_file))]

            if cmd is not None:
                logger.info("Running Popen cmd %s, with shell %s", cmd, shell)

                process = subprocess.Popen(cmd,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           shell=shell,
                                           cwd=cwd)

                try:
                    out_stream, err_stream = process.communicate(timeout=self.requirements_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning("The install command timed out, deleting the virtualenv")
                    shutil.rmtree(str(venv_path), ignore_errors=True)

                    raise BuildTimeoutError(f"Installing of requirements timeouted after "
                                            f"{self.requirements_timeout} seconds.")

                out_stream = out_stream.decode("utf-8")
                err_stream = err_stream.decode("utf-8")

                logger.debug("Return code is %s", process.returncode)
                logger.debug(out_stream)
                logger.debug(err_stream)

                if process.returncode:
                    logger.warning("The install command failed, deleting the virtualenv")
                    shutil.rmtree(str(venv_path), ignore_errors=True)
                    raise BuildError("Unable to install requirements.txt", extra_info={
                        "out_stream": out_stream,
                        "err_stream": err_stream,
                        "returncode": process.returncode
                    })

            else:
                logger.info("Requirements file not present in repo, empty venv it is.")
        else:
            logger.info(f"Venv already exists in {venv_path}")

        return venv_path

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> str:
        """ Handles the requirements in the target repository, returns a path to a executable of the virtualenv.
        """
        return str(self.get_or_create_venv(repo_path).resolve() / "bin" / "python")
