from __future__ import unicode_literals, print_function

from typing import Union


from .backend import BaseBackend, VenvBackend
from .result import Result
from .task import Task
from ._utils import load_class


BackendDefinitionType = Union[type, BaseBackend, str]


class Arca:

    def __init__(self, backend: BackendDefinitionType=VenvBackend):
        self.backend: BaseBackend = self._get_backend_instance(backend)

    def _get_backend_instance(self, backend: BackendDefinitionType) -> BaseBackend:
        if isinstance(backend, str):
            backend = load_class(backend)

        if isinstance(backend, type):
            backend = backend()

        if not issubclass(backend.__class__, VenvBackend):
            raise ValueError(f"{backend.__class__} is not an subclass of BaseBackend")

        return backend

    def run(self, repo: str, branch: str, task: Task) -> Result:
        return self.backend.run(repo, branch, task)
