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

    def get_virtualenv_name(self, requirements_file: Path) -> str:
        """
        Returns a name of the virtualenv that should be used for this repository.

        Either:

        * hash of the requirements file and Arca version
        * ``no_requirements_file`` if the requirements file doesn't exist.

        :param requirements_file: :class:`Path <pathlib.Path>` to where the requirements file
            should be in the cloned repository

        """
        if requirements_file is None:
            return "no_requirements_file"
        else:
            return self.get_requirements_hash(requirements_file)

    def get_or_create_venv(self, path: Path) -> Path:
        """
        Gets the name of the virtualenv from :meth:`get_virtualenv_name`, checks if it exists already,
        creates it and installs requirements otherwise. The virtualenvs are stored in a folder based
        on the :class:`Arca` ``base_dir`` setting.

        :param path: :class:`Path <pathlib.Path>` to the cloned repository.
        """
        requirements_file = self.get_requirements_file(path)
        venv_name = self.get_virtualenv_name(requirements_file)

        venv_path = Path(self._arca.base_dir) / "venvs" / venv_name

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

                try:
                    out_stream, err_stream = process.communicate(timeout=self.requirements_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    shutil.rmtree(venv_path, ignore_errors=True)

                    raise BuildTimeoutError(f"Installing of requirements timeouted after "
                                            f"{self.requirements_timeout} seconds.")

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

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> str:
        """ Handles the requirements in the target repository, returns a path to a executable of the virtualenv.
        """
        return str(self.get_or_create_venv(repo_path).resolve() / "bin" / "python")
