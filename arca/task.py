import re

from pathlib import Path
from typing import Optional, Tuple, Any, Dict, Iterable


class Task:

    def __init__(self, function_call: str, *,
                 imports: Optional[Iterable[str]]=None,
                 from_imports: Optional[Iterable[Tuple[str, str]]]=None,
                 args: Optional[Iterable[Any]]=None,
                 kwargs: Optional[Dict[str, Any]]=None):
        if re.match(r".*\s.*", function_call):
            raise ValueError("function_call contains a whitespace")  # TODO: custom exception

        self.function_call = function_call
        self.imports = list(imports or [])
        self.from_imports = list(from_imports or [])
        self.args = list(args or [])
        self.kwargs = dict(kwargs or {})

    def build_imports(self):
        return "\n".join([f"    import {x}" for x in self.imports])

    def build_from_imports(self):
        return "\n".join([f"    from {x[0]} import {x[1]}" for x in self.from_imports])

    def build_function_call(self):
        if len(self.args) and len(self.kwargs):
            return "{}(*{}, **{})".format(
                self.function_call,
                self.args,
                self.kwargs
            )
        elif len(self.args):
            return "{}(*{})".format(
                self.function_call,
                self.args
            )
        elif len(self.kwargs):
            return "{}(**{})".format(
                self.function_call,
                self.kwargs
            )
        else:
            return f"{self.function_call}()"

    def build_script(self, venv_path: Path) -> str:
        result = ""

        result += "#!" + str(venv_path.resolve() / "bin" / "python3") + "\n\n"
        result += "import json\n"
        result += "import traceback\n"
        result += "import sys\n"
        result += "import os\n"
        result += "sys.path.insert(1, os.getcwd())\n"
        result += "try:\n"

        result += self.build_imports() + "\n\n"
        result += self.build_from_imports() + "\n\n"

        result += f"""
    res = {self.build_function_call()}
    print(json.dumps({{"success": True, "result": res, "path": sys.path}}))
except:
    print(json.dumps({{"success": False, "error": traceback.format_exc(), "path": sys.path}}))
"""

        return result
