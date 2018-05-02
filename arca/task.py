import hashlib
import json
from typing import Optional, Any, Dict, Iterable

from cached_property import cached_property
from entrypoints import EntryPoint, BadEntryPoint

from .exceptions import TaskMisconfigured


class Task:
    """ A class for defining tasks the run in the repositories. The task is defined by an entry point,
    timeout (5 seconds by default), arguments and keyword arguments.
    The class uses :class:`entrypoints.EntryPoint` to load the callables.
    As apposed to :class:`EntryPoint <entrypoints.EntryPoint>`, only objects are allowed, not modules.

    Let's presume we have this function in a package ``library.module``:

    .. code-block:: python

        def ret_argument(value="Value"):
            return value

    This Task would return the default value:

    >>> Task("library.module:ret_argument")

    These two Tasks would returned an overridden value:

    >>> Task("library.module:ret_argument", args=["Overridden value"])
    >>> Task("library.module:ret_argument", kwargs={"value": "Overridden value"})
    """

    def __init__(self, entry_point: str, *,
                 timeout: int=5,
                 args: Optional[Iterable[Any]]=None,
                 kwargs: Optional[Dict[str, Any]]=None) -> None:

        try:
            self._entry_point = EntryPoint.from_string(entry_point, "task")
        except BadEntryPoint:
            raise TaskMisconfigured("Incorrectly defined entry point.")

        if self._entry_point.object_name is None:
            raise TaskMisconfigured("Task entry point must be an object, not a module.")

        try:
            self._timeout = int(timeout)

            if self._timeout < 1:
                raise ValueError
        except ValueError:
            raise TaskMisconfigured("Provided timeout could not be converted to int.")

        try:
            self._args = list(args or [])
            self._kwargs = dict(kwargs or {})
        except (TypeError, ValueError):
            raise TaskMisconfigured("Provided arguments cannot be converted to list or dict.")

        if not all([isinstance(x, str) for x in self._kwargs.keys()]):
            raise TaskMisconfigured("Keywords must be strings")

        try:
            assert isinstance(self.json, str)
        except (AssertionError, ValueError):
            raise TaskMisconfigured("Provided arguments are not JSON-serializable") from None

    @property
    def entry_point(self):
        return self._entry_point

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwargs

    @property
    def timeout(self):
        return self._timeout

    def __repr__(self):
        return f"Task({self.entry_point})"

    @cached_property
    def json(self):
        return json.dumps(self.serialized)

    @cached_property
    def serialized(self):
        import arca
        return {
            "version": arca.__version__,
            "entry_point": {
                "module_name": self._entry_point.module_name,
                "object_name": self._entry_point.object_name
            },
            "args": self._args,
            "kwargs": self._kwargs
        }

    @cached_property
    def hash(self):
        """ Returns a SHA1 hash of the Task for usage in cache keys.
        """
        return hashlib.sha256(bytes(self.json, "utf-8")).hexdigest()
