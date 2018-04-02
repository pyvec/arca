import hashlib
import json
import re
from pprint import pformat
from textwrap import dedent, indent
from typing import Optional, Any, Dict, Iterable

from cached_property import cached_property
from entrypoints import EntryPoint, BadEntryPoint

from .exceptions import TaskMisconfigured

custom_pattern = re.compile(r"[.\w]*:[.\w]*")


class Task:
    """ A class for defining tasks the run in the repositories. The task is defined by an entry point,
    arguments and keyword arguments. The class uses :class:`entrypoints.EntryPoint` to load the callables.
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
                 args: Optional[Iterable[Any]]=None,
                 kwargs: Optional[Dict[str, Any]]=None) -> None:

        if not custom_pattern.match(entry_point):
            raise TaskMisconfigured("Task entry point must be an object, not a module.")

        try:
            self._entry_point = EntryPoint.from_string(entry_point, "task")
        except BadEntryPoint:
            raise TaskMisconfigured("Incorrectly defined entry point.")

        self._args = list(args or [])
        self._kwargs = dict(kwargs or {})
        self._built_script: Optional[str] = None

    @property
    def entry_point(self):
        return self._entry_point

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwargs

    def __repr__(self):
        return f"Task({self.entry_point})"

    def build_function_call(self):
        if len(self.args) and len(self.kwargs):
            return "{!r}.load()(*{}, **{})".format(
                self.entry_point,
                pformat(self.args),
                pformat(self.kwargs)
            )
        elif len(self.args):
            return "{!r}.load()(*{})".format(
                self.entry_point,
                pformat(self.args)
            )
        elif len(self.kwargs):
            return "{!r}.load()(**{})".format(
                self.entry_point,
                pformat(self.kwargs)
            )
        else:
            return "{!r}.load()()".format(self.entry_point)

    def build_script(self) -> str:
        """ Returns a Python script for the Task, with all the required imports, serializing and error handling.
        """
        if self._built_script is not None:
            return self._built_script

        function_call = self.build_function_call()
        function_call = indent(function_call, " " * 12, lambda x: not x.startswith("EntryPoint"))

        script = dedent(f"""
        # encoding=utf-8
        import json
        import traceback
        import sys
        import os
        from importlib import import_module

        class EntryPoint:
            def __init__(self, name, module_name, object_name, *args, **kwargs):
                self.module_name = module_name
                self.object_name = object_name

            def load(self):
                mod = import_module(self.module_name)
                obj = mod
                for attr in self.object_name.split('.'):
                    obj = getattr(obj, attr)
                return obj

        sys.path.insert(1, os.getcwd())
        try:
            res = {function_call}
            print(json.dumps({{"success": True, "result": res}}))
        except:
            print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
        """)
        self._built_script = script

        return script

    @cached_property
    def hash(self):
        """ Returns a SHA1 hash of the Task for usage in cache keys.
        """
        return hashlib.sha1(bytes(json.dumps({
            "entry_point": self.entry_point.__repr__(),
            "args": self.args,
            "kwargs": self.kwargs,
        }), "utf-8")).hexdigest()
