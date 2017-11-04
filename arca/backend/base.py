import re
from pathlib import Path
from typing import Optional

from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty


class BaseBackend:

    verbosity: int = LazySettingProperty(key="verbosity", default=0)
    requirements_location: str = LazySettingProperty(key="requirements_location", default="requirements.txt")
    cwd: str = LazySettingProperty(key="cwd", default="")
    base_dir: str = LazySettingProperty(key="base_dir", default=".arca")

    def __init__(self, **settings):
        self._arca = None
        for key, val in settings.items():
            if hasattr(self, key) and isinstance(getattr(self, key), LazySettingProperty) and val is not NOT_SET:
                setattr(self, key, val)

    def inject_arca(self, arca):
        self._arca = arca

    def get_backend_name(self):
        # CamelCase -> camel_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.__class__.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def get_settings_keys(self, key):
        return f"{self.get_backend_name()}_{key}", f"backend_{key}"

    def get_setting(self, key, default=NOT_SET):
        return self._arca.settings.get(*self.get_settings_keys(key), default=default)

    def get_requirements_file(self, path: Path) -> Optional[Path]:
        requirements_file = path / self.requirements_location

        if not requirements_file.exists():
            return None
        return requirements_file

    def run(self, repo: str, branch: str, task: Task) -> Result:
        return self._run(repo, branch, task)

    def _run(self, repo: str, branch: str, task: Task) -> Result:  # pragma: no cover
        raise NotImplementedError

    def current_git_hash(self, repo: str, branch: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def create_environment(self, repo: str, branch: str, files_only: bool=False):  # pragma: no cover
        raise NotImplementedError

    def update_environment(self, repo: str, branch: str, files_only: bool=False):  # pragma: no cover
        raise NotImplementedError

    def environment_exists(self, repo: str, branch: str):  # pragma: no cover
        raise NotImplementedError

    def static_filename(self, repo: str, branch: str, relative_path: Path) -> Path:
        return self._static_filename(repo, branch, relative_path)

    def _static_filename(self, repo: str, branch: str, relative_path: Path) -> Path:  # pragma: no cover
        raise NotImplementedError
