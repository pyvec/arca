# encoding=utf-8
import datetime
import json

import pytest

from arca.exceptions import TaskMisconfigured
from arca.task import Task


@pytest.mark.parametrize("args,kwargs", [
    (None, None),
    ([], {}),
    ([{"x": 1}, [1, 2], (2, 3), "test", 1, 1.5, False, None], {
        "dict": {"x": 1},
        "list": [1, 2],
        "tuple": (2, 3),
        "str": "123",
        "int": 12,
        "float": 12.4,
        "bool": False,
        "none": None
    }),
    (range(5), None)
])
def test_task_json(args, kwargs):
    task = Task("library.mod:func", args=args, kwargs=kwargs)

    assert isinstance(json.loads(task.json), dict)
    assert task.hash


@pytest.mark.parametrize("args", "kwargs", [
    (1, None),
    (None, 1),
    (None, "123"),
    ([datetime.datetime.now()], None),
    (None, {"datetime": datetime.datetime.now()})
])
def task_task_arguments_validation(args, kwargs):
    with pytest.raises(TaskMisconfigured):
        Task("library.mod:func", args=args, kwargs=kwargs)


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
