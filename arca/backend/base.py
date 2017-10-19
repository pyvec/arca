import re
from pathlib import Path
from typing import Optional

from arca.task import Task


class BaseBackend:

    def __init__(self, *, verbosity=0, requirements_location="requirements.txt", cwd=None):
        self.verbosity = verbosity
        self.requirements_location = requirements_location
        if cwd is None:
            self.cwd = ""
        else:
            self.cwd = cwd

    def validate_repo_url(self, repo: str):
        # that should match valid git repos
        if not isinstance(repo, str) or not re.match(r"^(https?|file)://[\w._\-\/~]*[\.git]?\/?$", repo):
            # TODO: probably a custom exception would be better
            raise ValueError(f"{repo} is not a valid http[s] or file:// git repo")

    def repo_id(self, repo: str) -> str:
        if repo.startswith("http"):
            repo = re.sub(r"https?://(.www)?", "", repo)
            repo = re.sub(r"\.git/?$", "", repo)

            return "_".join(repo.split("/"))
        else:
            repo = repo.replace("file://", "")
            repo = re.sub(r"\.git/?$", "", repo)
            if repo.startswith("~"):
                repo = str(Path(repo).resolve())

            return "_".join(repo.split("/"))

    def get_requirements_file(self, path: Path) -> Optional[Path]:
        requirements_file = path / self.requirements_location

        if not requirements_file.exists():
            return None
        return requirements_file

    def create_environment(self, repo: str, branch: str, files_only: bool= False):
        raise NotImplementedError

    def update_environment(self, repo: str, branch: str, files_only: bool= False):
        raise NotImplementedError

    def environment_exists(self, repo: str, branch: str):
        raise NotImplementedError

    def run(self, repo: str, branch: str, task: Task):
        raise NotImplementedError

    def static_filename(self, repo: str, branch: str, relative_path: Path):
        raise NotImplementedError
