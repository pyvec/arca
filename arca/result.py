from typing import Dict, Union, Any


class Result:

    def __init__(self, result: Dict[str, Union[bool, str, Any]]) -> None:
        self.success = result.get("success")
        self._result = result.get("result")
        self._error = result.get("error")

    @property
    def error(self) -> str:
        if self.success:
            raise AttributeError("The task succeeded, there's no error")

        return self._error

    @property
    def result(self) -> Any:
        if not self.success:
            raise AttributeError("The task did not succeed, there's not result")

        return self._result
