import subprocess
from pathlib import Path
from venv import EnvBuilder

from git import Repo

import arca
from arca.exceptions import BuildError
from arca.utils import logger
from .base import BaseRunInSubprocessBackend


class VenvBackend(BaseRunInSubprocessBackend):

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
