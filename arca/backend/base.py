import re

from arca.task import Task


class BaseBackend:

    def __init__(self, *, verbosity=0, requirements_location="requirements.txt"):
        self.verbosity = verbosity
        self.requirements_location = requirements_location

    def validate_repo_url(self, repo: str):
        if not repo.startswith("http") or not repo.endswith(".git"):  # TODO: probably a regex would be better
            # TODO: probably a custom exception would be better
            raise ValueError(f"{repo} is not a valid http[s] git repo")

    def repo_id(self, repo: str) -> str:
        parts = re.sub(r".git$", "", repo).split("/")
        if len(parts) > 2:
            return "_".join(parts[-2:])
        return parts[-1]

    def create_environment(self, repo: str, branch: str):
        raise NotImplementedError

    def update_environment(self, repo: str, branch: str):
        raise NotImplementedError

    def environment_exists(self, repo: str, branch: str):
        raise NotImplementedError

    def run(self, repo: str, branch: str, task: Task):
        raise NotImplementedError
