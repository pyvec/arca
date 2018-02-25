# encoding=utf-8
import pytest
from pathlib import Path

from arca.exceptions import TaskMisconfigured
from arca.task import Task

ENV_PATH = Path("/usr")


def _clean_lines(x: str) -> str:
    return "\n".join([line.replace("\r", "") for line in x.split("\n") if line.replace("\r", "").strip()])


@pytest.mark.parametrize(["entry_point", "res"], (
    ("library:func", "EntryPoint('task', 'library', 'func', None)"),
    ("library.submodule:func", "EntryPoint('task', 'library.submodule', 'func', None)"),
    ("library.submodule:Obj", "EntryPoint('task', 'library.submodule', 'Obj', None)"),
))
def test_imports(entry_point, res):
    task = Task(entry_point)
    assert _clean_lines(task.build_script().split("sys.path.insert(1, os.getcwd())")[1]) == _clean_lines("""
try:
    res = {}.load()()
    print(json.dumps({{"success": True, "result": res}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
""".format(res))


@pytest.mark.parametrize(["args", "kwargs", "res"], (
    (None, None, "()"),
    ([], {}, "()"),
    ([1, "Test'\""], {}, """(*[1, 'Test\\'"'])"""),
    ([], {"test_1": 1, "test_2": "Test'\""}, """(**{'test_1': 1, 'test_2': 'Test\\'"'})"""),
    ([1, "Test'\""], {"test_1": 1, "test_2": "Test'\""},
     """(*[1, 'Test\\'"'], **{'test_1': 1, 'test_2': 'Test\\'"'})"""),
))
def test_arguments(args, kwargs, res):
    task = Task("library:func", args=args, kwargs=kwargs)
    assert _clean_lines(task.build_script().split("sys.path.insert(1, os.getcwd())")[1]) == _clean_lines("""
try:
    res = EntryPoint('task', 'library', 'func', None).load(){}
    print(json.dumps({{"success": True, "result": res}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
""".format(res))


@pytest.mark.parametrize("entry_point", [
    "library",
    "library.mod",
    "task=library.mod:func",
    "library.mod func",
    "library.mod:asdf asdf\nasdfasdf",
])
def test_invalid_entry_point(entry_point):
    with pytest.raises(TaskMisconfigured):
        Task(entry_point)
