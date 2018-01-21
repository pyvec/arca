from typing import Dict, Union, Any

from arca.exceptions import BuildError


class Result:

    def __init__(self, result: Dict[str, Union[bool, str, Any]]) -> None:
        if not result.get("success"):
            raise BuildError("The build failed", extra_info={
                "traceback": result.get("error")
            })

        self.output = result.get("result")
