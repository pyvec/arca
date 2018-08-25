import sys
from pathlib import Path

from git import Repo

from .base import BaseRunInSubprocessBackend


class CurrentEnvironmentBackend(BaseRunInSubprocessBackend):
    """ Uses the current Python to run the tasks, however they're launched in a :mod:`subprocess`.

    The requirements of the repository are completely ignored.
    """

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> str:
        """ Returns the path to the current Python executable.
        """
        return sys.executable
