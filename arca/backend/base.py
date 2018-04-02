import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from cached_property import cached_property
from git import Repo

import arca
from arca.exceptions import BuildError
from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty, logger


class BaseBackend:
    """ Abstract class for all the backends, implements some basic functionality.

    Available settings:

    * **requirements_location**: Relative path to the requirements file in the target repositories.
      (default is ``requirements.txt``)
    * **cwd**: Relative path to the required working directory. (default is ``""``, the root of the repo)
    """

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
        """ After backend is set for a :class:`Arca` instance, the instance is injected to the backend,
            so settings can be accessed, files accessed etc. Also runs settings validation of the backend.
        """
        self._arca = arca

        self.validate_settings()

    def validate_settings(self):
        pass

    @cached_property
    def snake_case_backend_name(self):
        """ CamelCase -> camel_case
        """
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.__class__.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def get_settings_keys(self, key):
        """
        Parameters can be set through two settings keys, by a specific setting (eg. ``ARCA_DOCKER_BACKEND_KEY``)
        or a general ``ARCA_BACKEND_KEY``. This function returns the two keys that can be used for this setting.
        """
        return f"{self.snake_case_backend_name}_{key}", f"backend_{key}"

    def get_setting(self, key, default=NOT_SET):
        """ Gets a setting for the key.

        :raise KeyError: If the key is not set and default isn't provided.
        """
        return self._arca.settings.get(*self.get_settings_keys(key), default=default)

    def get_requirements_file(self, path: Path) -> Optional[Path]:
        """
        Gets a :class:`Path <pathlib.Path>` for the requirements file if it exists in the provided ``path``,
        returns ``None`` otherwise.
        """
        if not self.requirements_location:
            return None

        requirements_file = path / self.requirements_location

        if not requirements_file.exists():
            return None
        return requirements_file

    def create_script(self, task: Task) -> Tuple[str, str]:
        """ Returns the generated script from the Task and it's name.
        """
        script = task.build_script()
        script_hash = hashlib.sha1(bytes(script, "utf-8")).hexdigest()

        return f"{script_hash}.py", script

    def get_requirements_hash(self, requirements_file: Path) -> str:
        """ Returns an SHA1 hash of the contents of the ``requirements_path``.
        """
        logger.debug("Hashing: %s%s", requirements_file.read_text(), arca.__version__)
        return hashlib.sha1(bytes(requirements_file.read_text() + arca.__version__, "utf-8")).hexdigest()

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:  # pragma: no cover
        """
        Executes the script and returns the result.

        Must be implemented by subclasses.

        :param repo: Repo URL
        :param branch: Branch name
        :param task: The requested :class:`Task`
        :param git_repo: A :class:`Repo <git.repo.base.Repo>` of the repo/branch
        :param repo_path: :class:`Path <pathlib.Path>` to the location where the repo is stored.
        :return: The output of the task in a :class:`Result` instance.
        """
        raise NotImplementedError


class BaseRunInSubprocessBackend(BaseBackend):
    """ Abstract class for backends which run scripts in :mod:`subprocess`.
    """

    def get_or_create_environment(self, repo: str, branch: str,
                                  git_repo: Repo, repo_path: Path) -> str:  # pragma: no cover
        """
        Abstract method which must be implemented in subclasses, which must return a str path to a Python executable
        which will be used to run the script.

        See :meth:`BaseBackend.run <arca.BaseBackend.run>` to see arguments description.
        """
        raise NotImplementedError

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path) -> Result:
        """
        Gets a path to a Python executable by calling the abstract method
        :meth:`get_image_for_repo <BaseRunInSubprocessBackend.get_image_for_repo>`
        and runs the task using :class:`subprocess.Popen`

        See :meth:`BaseBackend.run <arca.BaseBackend.run>` to see arguments description.
        """
        python_path = self.get_or_create_environment(repo, branch, git_repo, repo_path)

        script_name, script = self.create_script(task)
        script_path = Path(self._arca.base_dir, "scripts", script_name)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script)

        logger.info("Stored task script at %s", script_path)

        st = os.stat(str(script_path))
        script_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        out_output = ""
        err_output = ""

        cwd = str(repo_path / self.cwd)

        logger.info("Running at cwd %s", cwd)

        try:
            logger.debug("Running with python %s", python_path)

            process = subprocess.Popen([python_path, str(script_path.resolve())],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       cwd=cwd)

            out_stream, err_stream = process.communicate()

            out_output = out_stream.decode("utf-8")
            err_output = err_stream.decode("utf-8")

            logger.debug("stdout output from the command")
            logger.debug(out_output)

            return Result(json.loads(out_output))
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e,
                "out_output": out_output,
                "err_output": err_output,
            })
