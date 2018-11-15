import json
from typing import Dict, Any, Union

from arca.exceptions import BuildError


class Result:
    """ For storing results of the tasks. So far only has one attribute, :attr:`output`.
    """

    def __init__(self, result: Union[str, Dict[str, Any]]) -> None:
        if isinstance(result, (str, bytes, bytearray)):
            output = result
            try:
                result = json.loads(result)
            except ValueError:
                raise BuildError("The build failed (the output was corrupted, "
                                 "possibly by the callable printing something)",
                                 extra_info={
                                     "output": output
                                 })

        if not isinstance(result, dict):
            raise BuildError("The build failed (the value returned from the runner was not valid)")

        if not result.get("success"):
            reason = "Task failed"
            if result.get("reason") == "corrupted_definition":
                reason = "Task failed because the definition was corrupted."
            elif result.get("reason") == "import":
                reason = "Task failed beucase the entry point could not be imported"

            raise BuildError(reason, extra_info={
                "traceback": result.get("error")
            })

        #: The output of the task
        self.output = result.get("result")

        #: What the function wrote to stdout
        self.stdout = result.get("stdout")

        #: What the function wrote to stderr
        self.stderr = result.get("stderr")
