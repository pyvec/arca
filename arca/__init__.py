from ._arca import Arca
from .backend import BaseBackend, VenvBackend, DockerBackend, CurrentEnvironmentBackend, RequirementsStrategy, \
    VagrantBackend
from .result import Result
from .task import Task


__all__ = ["Arca", "BaseBackend", "VenvBackend", "DockerBackend", "Result", "Task", "CurrentEnvironmentBackend",
           "RequirementsStrategy", "VagrantBackend"]
__version__ = "0.2.0"
