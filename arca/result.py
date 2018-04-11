from typing import Dict, Union, Any

from arca.exceptions import BuildError


class Result:
    """ For storing results of the tasks. So far only has one attribute, :attr:`output`.
    """

    def __init__(self, result: Dict[str, Any]) -> None:
        if not result.get("success"):
            raise BuildError("The build failed", extra_info={
                "traceback": result.get("error")
            })

        #: The output of the task
        self.output = result.get("result")
