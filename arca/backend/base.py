import re
from pathlib import Path
from typing import Optional

from arca.task import Task
from arca.utils import NOT_SET


class BaseBackend:

    def __init__(self, *, verbosity=NOT_SET, requirements_location=NOT_SET, cwd=NOT_SET):
        self._arca = None
        self.verbosity = verbosity
        self.requirements_location = requirements_location
        self.cwd = cwd

    def inject_arca(self, arca):
        self._arca = arca

        self.verbosity = self.get_setting("verbosity", 0) \
            if self.verbosity is NOT_SET else self.verbosity

        self.requirements_location = self.get_setting("requirements_location", "requirements.txt") \
            if self.requirements_location is NOT_SET else self.requirements_location

        self.cwd = self.get_setting("cwd", "") \
            if self.cwd is NOT_SET else self.cwd

    def get_backend_name(self):
        # CamelCase -> camel_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.__class__.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def get_settings_keys(self, key):
        return f"{self.get_backend_name()}_{key}", f"backend_{key}"

    def get_setting(self, key, default=NOT_SET):
        return self._arca.settings.get(*self.get_settings_keys(key), default=default)

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
