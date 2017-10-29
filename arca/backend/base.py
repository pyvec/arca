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

    def __init__(self, **settings):
        from .._arca import Arca  # noqa

        self._arca: Arca = None
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

    def cache_key(self, repo: str, branch: str, task: Task) -> str:
        return "{repo}_{branch}_{hash}_{task}".format(repo=self.repo_id(repo), branch=branch,
                                                      hash=self.current_git_hash(repo, branch),
                                                      task=task.serialize())

    def run(self, repo: str, branch: str, task: Task) -> Result:
        self.validate_repo_url(repo)

        def create_value():
            return self._run(repo, branch, task)

        def should_cache(value: Result):
            return value.success

        return self._arca.region.get_or_create(
            self.cache_key(repo, branch, task),
            create_value,
            should_cache_fn=should_cache
        )

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
        self.validate_repo_url(repo)
        return self._static_filename(repo, branch, relative_path)

    def _static_filename(self, repo: str, branch: str, relative_path: Path) -> Path:  # pragma: no cover
        raise NotImplementedError
