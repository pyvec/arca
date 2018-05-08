import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Optional, Iterable, Set

from git import Repo

from arca.exceptions import ArcaMisconfigured, RequirementsMismatch, BuildError, BuildTimeoutError
from arca.utils import LazySettingProperty, logger
from .base import BaseRunInSubprocessBackend


class RequirementsStrategy(Enum):
    """ Enum for defining strategy for :class:`CurrentEnvironmentBackend`
    """

    #: Ignores all difference of requirements of the current environment and the target repository.
    IGNORE = "ignore"

    #: Raises an exception if there are some extra requirements in the target repository.
    RAISE = "raise"

    #: Installs the extra requirements.
    INSTALL_EXTRA = "install_extra"


class CurrentEnvironmentBackend(BaseRunInSubprocessBackend):
    """ Uses the current Python to run the tasks, however they're launched in a :mod:`subprocess`.

    Available settings:

    * **current_environment_requirements**: Path to the requirements file of the current requirements.
      Set to ``None`` if there are none. (default is ``requirements.txt``)

    * **requirements_strategy**: How should requirements differences be handled.
      Can be either strings or a :class:`RequirementsStrategy` value.
      See the :class:`RequirementsStrategy` Enum for available strategies
      (default is :attr:`RequirementsStrategy.RAISE`)

    """

    current_environment_requirements = LazySettingProperty(default="requirements.txt")
    requirements_strategy = LazySettingProperty(default=RequirementsStrategy.RAISE,
                                                convert=RequirementsStrategy)

    def install_requirements(self, *, path: Optional[Path] = None, requirements: Optional[Iterable[str]] = None,
                             _action: str = "install"):
        """
        Installs requirements, either from a file or from a iterable of strings.

        :param path: :class:`Path <pathlib.Path>` to a ``requirements.txt`` file. Has priority over ``requirements``.
        :param requirements: A iterable of strings of requirements to install.
        :param _action: For testing purposes, can be either ``install`` or ``uninstall``

        :raise BuildError: If installing fails.
        :raise ValueError: If both ``file`` and ``requirements`` are undefined.
        :raise ValueError: If ``_action`` not ``install`` or ``uninstall``.
        """
        if _action not in ["install", "uninstall"]:
            raise ValueError(f"{_action} is invalid value for _action")

        cmd = [sys.executable, "-m", "pip", _action]

        if _action == "uninstall":
            cmd += ["-y"]

        if path is not None:
            cmd += ["-r", str(path)]
        elif requirements is not None:
            cmd += list(requirements)
        else:
            raise ValueError("Either path or requirements has to be provided")

        logger.info("Installing requirements with command: %s", cmd)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            out_stream, err_stream = process.communicate(timeout=self.requirements_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            raise BuildTimeoutError(f"Installing of requirements timeouted after {self.requirements_timeout} seconds.")

        out_stream = out_stream.decode("utf-8")
        err_stream = err_stream.decode("utf-8")

        logger.debug("Return code is %s", process.returncode)
        logger.debug(out_stream)
        logger.debug(err_stream)

        if process.returncode:
            raise BuildError(f"Unable to {_action} requirements from the target repository", extra_info={
                "out_stream": out_stream,
                "err_stream": err_stream,
                "returncode": process.returncode
            })

    def get_requirements_set(self, file: Path) -> Set[str]:
        """
        :param file: :class:`Path <pathlib.Path>` to a ``requirements.txt`` file.
        :return: Set of the requirements from the file with newlines and extra characters removed.
        """
        return set([x.strip() for x in file.read_text().split("\n") if x.strip()])

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> str:
        """
        Handles the requirements of the target repository (based on ``requirements_strategy``) and returns
        the path to the current Python executable.
        """
        self.handle_requirements(repo, branch, repo_path)

        return sys.executable

    def handle_requirements(self, repo: str, branch: str, repo_path: Path):
        """ Checks the differences and handles it using the selected strategy.
        """
        if self.requirements_strategy == RequirementsStrategy.IGNORE:
            logger.info("Requirements strategy is IGNORE")
            return

        requirements = repo_path / self.requirements_location

        # explicitly configured there are no requirements for the current environment
        if self.current_environment_requirements is None:

            if not requirements.exists():
                return  # no diff, since no requirements both in current env and repository

            requirements_set = self.get_requirements_set(requirements)

            if len(requirements_set):
                if self.requirements_strategy == RequirementsStrategy.RAISE:
                    raise RequirementsMismatch(f"There are extra requirements in repository {repo}, branch {branch}.",
                                               diff=requirements.read_text())

                self.install_requirements(path=requirements)

        # requirements for current environment configured
        else:
            current_requirements = Path(self.current_environment_requirements)

            if not requirements.exists():
                return  # no req. file in repo -> no extra requirements

            logger.info("Searching for current requirements at absolute path %s", current_requirements)
            if not current_requirements.exists():
                raise ArcaMisconfigured("Can't locate current environment requirements.")

            current_requirements_set = self.get_requirements_set(current_requirements)

            requirements_set = self.get_requirements_set(requirements)

            # only requirements that are extra in repository requirements matter
            extra_requirements_set = requirements_set - current_requirements_set

            if len(extra_requirements_set) == 0:
                return  # no extra requirements in repository
            else:
                if self.requirements_strategy == RequirementsStrategy.RAISE:
                    raise RequirementsMismatch(f"There are extra requirements in repository {repo}, branch {branch}.",
                                               diff="\n".join(extra_requirements_set))

                elif self.requirements_strategy == RequirementsStrategy.INSTALL_EXTRA:
                    self.install_requirements(requirements=extra_requirements_set)

    def _uninstall(self, *args):
        """ For usage in tests to uninstall packages from the current environment

        :param args: packages to uninstall
        """
        self.install_requirements(requirements=args, _action="uninstall")
