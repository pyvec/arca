# encoding=utf-8
import pytest

from arca.result import Result


def test_success():
    res = Result({"success": True, "result": "Message"})
    assert res.success
    assert res.result == "Message"
    with pytest.raises(AttributeError):
        res.error

    res2 = Result({"success": True, "result": 1})
    assert res2.success
    assert res2.result == 1
    with pytest.raises(AttributeError):
        res2.error


def test_error():
    res = Result({"success": False, "error": "Error"})
    assert not res.success
    assert res.error == "Error"
    with pytest.raises(AttributeError):
        res.result
