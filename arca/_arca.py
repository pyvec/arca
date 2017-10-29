import json
import os
from pathlib import Path
from typing import Union, Optional, Dict, Any

from dogpile.cache import make_region, CacheRegion

from .backend import BaseBackend, VenvBackend
from .result import Result
from .task import Task
from .utils import load_class, Settings, NOT_SET

BackendDefinitionType = Union[type, BaseBackend, str]


class Arca:

    def __init__(self, backend: BackendDefinitionType=NOT_SET, settings=None):
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
            settings = Settings(settings)
        else:
            settings = Settings()

        for key, val in os.environ.items():
            if key.startswith(Settings.PREFIX):
                settings[key] = val

        return settings

    def _make_region(self) -> CacheRegion:
        arguments = self.get_setting("cache_backend_arguments", None)

        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        return make_region().configure(
            self.get_setting("cache_backend", "dogpile.cache.null"),
            expiration_time=self.get_setting("cache_expiration_time", None),
            arguments=arguments
        )

    def get_setting(self, key, default=NOT_SET):
        return self.settings.get(key, default=default)

    def run(self, repo: str, branch: str, task: Task) -> Result:
        return self.backend.run(repo, branch, task)

    def static_filename(self, repo: str, branch: str, relative_path: Union[str, Path]) -> Path:
        if not isinstance(relative_path, Path):
            relative_path = Path(relative_path)
        return self.backend.static_filename(repo, branch, relative_path)
