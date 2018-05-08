import hashlib
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from cached_property import cached_property
from git import Repo

import arca
from arca.exceptions import BuildError, BuildTimeoutError
from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty, logger


class BaseBackend:
    """ Abstract class for all the backends, implements some basic functionality.

    Available settings:

    * **requirements_location**: Relative path to the requirements file in the target repositories.
      (default is ``requirements.txt``)
    * **requirements_timeout**: The maximum time in seconds allowed for installing requirements.
      (default is 5 minutes, 300 seconds)
    * **cwd**: Relative path to the required working directory.
      (default is ``""``, the root of the repo)
    """

    RUNNER = Path(__file__).parent.parent.resolve() / "_runner.py"

    requirements_location: str = LazySettingProperty(default="requirements.txt")
    requirements_timeout: int = LazySettingProperty(default=300, convert=int)
    cwd: str = LazySettingProperty(default="")

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

        self.validate_configuration()

    def validate_configuration(self):
        pass

    @cached_property
    def snake_case_backend_name(self):
        """ CamelCase -> camel_case
        """
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', type(self).__name__)
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
        if self._arca is None:
            raise LazySettingProperty.SettingsNotReady
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

    def serialized_task(self, task: Task) -> Tuple[str, str]:
        """ Returns the name of the task definition file and its contents.
        """
        return f"{task.hash}.json", task.json

    def get_requirements_hash(self, requirements_file: Path) -> str:
        """ Returns an SHA1 hash of the contents of the ``requirements_path``.
        """
        logger.debug("Hashing: %s%s", requirements_file.read_text(), arca.__version__)
        return hashlib.sha256(bytes(requirements_file.read_text() + arca.__version__, "utf-8")).hexdigest()

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

        task_filename, task_json = self.serialized_task(task)

        task_path = Path(self._arca.base_dir, "tasks", task_filename)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(task_json)

        logger.info("Stored task definition at %s", task_path)

        out_output = ""
        err_output = ""

        cwd = str(repo_path / self.cwd)

        logger.info("Running at cwd %s", cwd)

        try:
            logger.debug("Running with python %s", python_path)

            process = subprocess.Popen([python_path,
                                        str(self.RUNNER),
                                        str(task_path.resolve())],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       cwd=cwd)

            try:
                out_stream, err_stream = process.communicate(timeout=task.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                raise BuildTimeoutError(f"The task timeouted after {task.timeout} seconds.")

            out_output = out_stream.decode("utf-8")
            err_output = err_stream.decode("utf-8")

            logger.debug("stdout output from the command")
            logger.debug(out_output)

            return Result(out_output)
        except BuildError:  # can be raised by  :meth:`Result.__init__` or by timeout
            raise
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e,
                "out_output": out_output,
                "err_output": err_output,
            })
