import hashlib
import json
import re
from pprint import pformat
from textwrap import dedent, indent
from typing import Optional, Any, Dict, Iterable

from entrypoints import EntryPoint, BadEntryPoint

from .exceptions import TaskMisconfigured

custom_pattern = re.compile(r"[.\w]*:[.\w]*")


class Task:

    def __init__(self, entry_point: str, *,
                 args: Optional[Iterable[Any]]=None,
                 kwargs: Optional[Dict[str, Any]]=None) -> None:

        if not custom_pattern.match(entry_point):
            raise TaskMisconfigured("Task entry point must be an object, not a module.")

        try:
            self.entry_point = EntryPoint.from_string(entry_point, "task")
        except BadEntryPoint:
            raise TaskMisconfigured("Incorrectly defined entry point.")

        self.args = list(args or [])
        self.kwargs = dict(kwargs or {})

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
        function_call = self.build_function_call()
        function_call = indent(function_call, "            ", lambda x: not x.startswith("EntryPoint"))

        return dedent(f"""
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

    def serialize(self):
        return hashlib.sha1(bytes(json.dumps({
            "entry_point": self.entry_point.__repr__(),
            "args": self.args,
            "kwargs": self.kwargs,
        }), "utf-8")).hexdigest()
