""" This file is the code which actually launches the tasks, the serialized JSONs.
"""
import contextlib
import io
import json
import os
import sys
import traceback
from importlib import import_module
from pathlib import Path

sys.path.insert(1, os.getcwd())


class EntryPoint:
    def __init__(self, module_name, object_name):
        self.module_name = module_name
        self.object_name = object_name

    def load(self):
        mod = import_module(self.module_name)
        obj = mod
        for attr in self.object_name.split('.'):
            obj = getattr(obj, attr)

        return obj


def run(filename):
    try:

        task_definition = json.loads(Path(filename).read_text())

        entry_point = EntryPoint(task_definition["entry_point"]["module_name"],
                                 task_definition["entry_point"]["object_name"])

        args = task_definition["args"]
        kwargs = task_definition["kwargs"]

        if not isinstance(args, list):
            raise ValueError("args is not a list")

        if not isinstance(kwargs, dict) or not all([isinstance(x, str) for x in kwargs.keys()]):
            raise ValueError("kwargs is not a valid kwargs dict")

    except (ValueError, KeyError, TypeError, AttributeError):
        # ValueError: the json can be corrupted, args and kwargs can be invalid
        # KeyError: keys can be missing from the parsed json
        # TypeError: task_definition["entry_point"] is a list
        # AttributeError: task_definition["entry_point"] isn't a dict
        return {"success": False, "reason": "corrupted_definition", "error": traceback.format_exc()}

    try:
        entry_point = entry_point.load()
    except (ImportError, AttributeError):
        return {"success": False, "reason": "import", "error": traceback.format_exc()}

    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            res = entry_point(*args, **kwargs)
    except BaseException:
        return {"success": False, "error": traceback.format_exc()}

    return {"success": True,
            "result": res,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue()}


if __name__ == "__main__":
    # <script> <json>
    print(json.dumps(run(sys.argv[1])))
