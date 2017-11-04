import json
import os
from pathlib import Path
from typing import Union, Optional, Dict, Any

import re
from dogpile.cache import make_region, CacheRegion

from .backend import BaseBackend
from .result import Result
from .task import Task
from .utils import load_class, Settings, NOT_SET

BackendDefinitionType = Union[type, BaseBackend, str]


class Arca:

    def __init__(self, backend: BackendDefinitionType=NOT_SET, settings=None) -> None:
        self.settings: Settings = self._get_settings(settings)

        self.region: CacheRegion = self._make_region()

        self.backend: BaseBackend = self._get_backend_instance(backend)
        self.backend.inject_arca(self)

    def _get_backend_instance(self, backend: BackendDefinitionType) -> BaseBackend:
        if backend is NOT_SET:
            backend = self.get_setting("backend", "arca.backend.VenvBackend")

        if isinstance(backend, str):
            backend = load_class(backend)

        if isinstance(backend, type):
            backend = backend()

        if not issubclass(backend.__class__, BaseBackend):
            raise ValueError(f"{backend.__class__} is not an subclass of BaseBackend")

        return backend

    def _get_settings(self, settings: Optional[Dict[str, Any]]) -> Settings:
        if settings is not None:
            _settings = Settings(settings)
        else:
            _settings = Settings()

        for key, val in os.environ.items():
            if key.startswith(Settings.PREFIX):
                _settings[key] = val

        return _settings

    def _make_region(self) -> CacheRegion:
        arguments = self.get_setting("cache_backend_arguments", None)

        if isinstance(arguments, str):
            arguments = json.loads(arguments)  # TODO: catch errors and raise custom exception

        return make_region().configure(
            self.get_setting("cache_backend", "dogpile.cache.null"),
            expiration_time=self.get_setting("cache_expiration_time", None),
            arguments=arguments
        )

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

    def get_setting(self, key: str, default=NOT_SET):
        return self.settings.get(key, default=default)

    def cache_key(self, repo: str, branch: str, task: Task) -> str:
        return "{repo}_{branch}_{hash}_{task}".format(repo=self.repo_id(repo), branch=branch,
                                                      hash=self.backend.current_git_hash(repo, branch),
                                                      task=task.serialize())

    def run(self, repo: str, branch: str, task: Task) -> Result:
        self.validate_repo_url(repo)

        def create_value():
            return self.backend.run(repo, branch, task)

        def should_cache(value: Result):
            return value.success

        return self.region.get_or_create(
            self.cache_key(repo, branch, task),
            create_value,
            should_cache_fn=should_cache
        )

    def static_filename(self, repo: str, branch: str, relative_path: Union[str, Path]) -> Path:
        self.validate_repo_url(repo)

        if not isinstance(relative_path, Path):
            relative_path = Path(relative_path)
        return self.backend.static_filename(repo, branch, relative_path)

    def pull_again(self, repo: Optional[str]=None, branch: Optional[str]=None):
        return self.backend.pull_again(repo, branch)
