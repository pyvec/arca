# encoding=utf-8
import pytest

from arca.exceptions import BuildError
from arca.result import Result


def test_success():
    res = Result({"success": True, "result": "Message"})
    assert res.output == "Message"

    res2 = Result({"success": True, "result": 1})
    assert res2.output == 1


def test_error():
    with pytest.raises(BuildError):
        Result({"success": False, "error": "Error"})
