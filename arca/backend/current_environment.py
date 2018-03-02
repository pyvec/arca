import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Optional, Iterable

from git import Repo

from arca.exceptions import ArcaMisconfigured, RequirementsMismatch, BuildError
from arca.utils import LazySettingProperty, logger
from .base import BaseRunInSubprocessBackend


class RequirementsStrategy(Enum):
    IGNORE = "ignore"
    RAISE = "raise"
    INSTALL_EXTRA = "install_extra"


class CurrentEnvironmentBackend(BaseRunInSubprocessBackend):

    current_environment_requirements = LazySettingProperty(key="current_environment_requirements",
                                                           default="requirements.txt")
    requirements_strategy = LazySettingProperty(key="requirements_strategy",
                                                default=RequirementsStrategy.RAISE,
                                                convert=RequirementsStrategy)

    def install_requirements(self, *, fl: Optional[Path]=None, requirements: Optional[Iterable[str]]=None,
                             _action: str="install"):
        if _action not in ["install", "uninstall"]:
            raise ValueError(f"{_action} is invalid value for _action")

        cmd = [sys.executable, "-m", "pip", _action]

        if _action == "uninstall":
            cmd += ["-y"]

        if fl is not None:
            cmd += ["-r", str(fl)]
        elif requirements is not None:
            cmd += list(requirements)
        else:
            raise ValueError("Either fl or requirements has to be provided")

        logger.info("Installing requirements with command: %s", cmd)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        [out_stream, err_stream] = process.communicate()
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

    def get_requirements_set(self, fl):
        return set([x.strip() for x in fl.read_text().split("\n") if x.strip()])

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path):
        """ Handles requirements difference based on configured strategy
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

                self.install_requirements(fl=requirements)

        # requirements for current environment configured
        else:
            current_requirements = Path(self.current_environment_requirements)

            if not requirements.exists():
                return  # no req. file in repo -> no extra requirements

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
