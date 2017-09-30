# encoding=utf-8
import pytest
from pathlib import Path

from arca.task import Task

env_path = Path("/usr")


def _clean_lines(x: str) -> str:
    return "\n".join([line for line in x.split("\n") if line.strip()])


@pytest.mark.parametrize(["imports", "res"], (
    (None, ""),
    ([], ""),
    (set(), ""),
    (["single_import"], "import single_import"),
    (["more_imports", "more_imports.second"], "import more_imports\n    import more_imports.second\n"),
    ({"import_from_set"}, "import import_from_set"),
))
def test_imports(imports, res):
    task = Task("func", imports=imports)
    assert _clean_lines(task.build_script(env_path)) == _clean_lines("""#!/usr/bin/python3
import json
import traceback
try:
    {}
    res = func()
    print(json.dumps({{"success": True, "result": res}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
""".format(res))


@pytest.mark.parametrize(["from_imports", "res"], (
    (None, ""),
    ([], ""),
    (set(), ""),
    ([("single_import", "Things")], "from single_import import Things"),
    ([("more_imports", "Thing"), ("multiple_imports", "SecondThing")],
     "from more_imports import Thing\n    from multiple_imports import SecondThing\n")
))
def test_from_imports(from_imports, res):
    task = Task("func", from_imports=from_imports)
    assert _clean_lines(task.build_script(env_path)) == _clean_lines("""#!/usr/bin/python3
import json
import traceback
try:
    {}
    res = func()
    print(json.dumps({{"success": True, "result": res}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
""".format(res))


@pytest.mark.parametrize(["args", "kwargs", "res"], (
    (None, None, "func()"),
    ([], {}, "func()"),
    ([1, "Test'\""], {}, """func(*[1, 'Test\\'"'])"""),
    ([], {"test_1": 1, "test_2": "Test'\""}, """func(**{'test_1': 1, 'test_2': 'Test\\'"'})"""),
    ([1, "Test'\""], {"test_1": 1, "test_2": "Test'\""},
     """func(*[1, 'Test\\'"'], **{'test_1': 1, 'test_2': 'Test\\'"'})"""),
))
def test_function_call(args, kwargs, res):
    task = Task("func", args=args, kwargs=kwargs)
    assert _clean_lines(task.build_script(env_path)) == _clean_lines("""#!/usr/bin/python3
import json
import traceback
try:
    res = {}
    print(json.dumps({{"success": True, "result": res}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc()}}))
""".format(res))
