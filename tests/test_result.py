# encoding=utf-8
import pytest

from arca.result import Result


def test_success():
    res = Result({"success": True, "text": "Message"})
    assert res.success
    assert res.text == "Message"
    with pytest.raises(AttributeError):
        res.error


def test_error():
    res = Result({"success": False, "error": "Error"})
    assert not res.success
    assert res.error == "Error"
    with pytest.raises(AttributeError):
        res.text
