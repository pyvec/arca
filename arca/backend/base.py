import hashlib
import re
from pathlib import Path
from typing import Optional, Tuple

from git import Repo

import arca
from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty


class BaseBackend:

    verbosity: int = LazySettingProperty(key="verbosity", default=0)
    requirements_location: str = LazySettingProperty(key="requirements_location", default="requirements.txt")
    cwd: str = LazySettingProperty(key="cwd", default="")

    def __init__(self, **settings):
        self._arca = None
        for key, val in settings.items():
            if hasattr(self, key) and isinstance(getattr(self, key), LazySettingProperty) and val is not NOT_SET:
                setattr(self, key, val)

    def inject_arca(self, arca):
        self._arca = arca

        self.validate_settings()

    def validate_settings(self):
        pass

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

    def create_script(self, task: Task, venv_path: Path=None) -> Tuple[str, str]:
        script = task.build_script(venv_path)
        script_hash = hashlib.sha1(bytes(script, "utf-8")).hexdigest()

        return f"{script_hash}.py", script

    def get_requirements_hash(self, requirements_file) -> str:
        return hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__, "utf-8")).hexdigest()

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:  # pragma: no cover
        raise NotImplementedError

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path):  # pragma: no cover
        raise NotImplementedError
