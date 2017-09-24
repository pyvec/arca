# encoding=utf-8
from typing import Dict, Union


class Result:

    def __init__(self, result: Dict[str, Union[bool, str]]):
        self.success = result.get("success")
        self._text = result.get("text")
        self._error = result.get("error")

    @property
    def error(self) -> str:
        if self.success:
            raise AttributeError("The task succeeded, there's no error")

        return self._error

    @property
    def text(self) -> str:
        if not self.success:
            raise AttributeError("The task did not succeed, there's not text")

        return self._text
