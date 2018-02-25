import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from git import Repo

import arca
from arca.exceptions import BuildError
from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty, logger


class BaseBackend:

    verbosity: int = LazySettingProperty(key="verbosity", default=0)
    requirements_location: str = LazySettingProperty(key="requirements_location", default="requirements.txt")
    cwd: str = LazySettingProperty(key="cwd", default="")

    def __init__(self, **settings):
        self._arca = None
        for key, val in settings.items():
            if hasattr(self, key) and isinstance(getattr(self, key), LazySettingProperty) and val is not NOT_SET:
                if getattr(self, key).convert is not None:
                    val = getattr(self, key).convert(val)
                setattr(self, key, val)

    def inject_arca(self, arca):
        self._arca = arca

        self.validate_settings()

    def validate_settings(self):
        pass

    def get_backend_name(self):
        # CamelCase -> camel_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.__class__.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def get_settings_keys(self, key):
        return f"{self.get_backend_name()}_{key}", f"backend_{key}"

    def get_setting(self, key, default=NOT_SET):
        return self._arca.settings.get(*self.get_settings_keys(key), default=default)

    def get_requirements_file(self, path: Path) -> Optional[Path]:
        requirements_file = path / self.requirements_location

        if not requirements_file.exists():
            return None
        return requirements_file

    def create_script(self, task: Task, venv_path: Path=None) -> Tuple[str, str]:
        script = task.build_script()
        script_hash = hashlib.sha1(bytes(script, "utf-8")).hexdigest()

        return f"{script_hash}.py", script

    def get_requirements_hash(self, requirements_file) -> str:
        return hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__, "utf-8")).hexdigest()

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:  # pragma: no cover
        raise NotImplementedError

    def get_or_create_environment(self, repo: str, branch: str, git_repo: Repo, repo_path: Path):  # pragma: no cover
        raise NotImplementedError


class BaseRunInSubprocessBackend(BaseBackend):

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:
        venv_path = self.get_or_create_environment(repo, branch, git_repo, repo_path)

        script_name, script = self.create_script(task, venv_path)
        script_path = Path(self._arca.base_dir, "scripts", script_name)
        script_path.parent.mkdir(parents=True, exist_ok=True)

        with script_path.open("w") as f:
            f.write(script)

        st = os.stat(str(script_path))
        script_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        out_stream = b""
        err_stream = b""

        cwd = str(repo_path / self.cwd)

        logger.info("Running at cwd %s", cwd)

        try:
            if venv_path is not None:
                python_path = str(venv_path.resolve() / "bin" / "python")
            else:
                python_path = sys.executable

            process = subprocess.Popen([python_path, str(script_path.resolve())],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       cwd=cwd)

            out_stream, err_stream = process.communicate()

            return Result(json.loads(out_stream.decode("utf-8")))
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e,
                "out_stream": out_stream,
                "err_stream": err_stream,
            })
