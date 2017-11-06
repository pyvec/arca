import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple

from git import Repo

from arca.result import Result
from arca.task import Task
from arca.utils import NOT_SET, LazySettingProperty, logger


class BaseBackend:

    verbosity: int = LazySettingProperty(key="verbosity", default=0)
    requirements_location: str = LazySettingProperty(key="requirements_location", default="requirements.txt")
    cwd: str = LazySettingProperty(key="cwd", default="")
    base_dir: str = LazySettingProperty(key="base_dir", default=".arca")
    single_pull: str = LazySettingProperty(key="single_pull", default=False)

    def __init__(self, **settings):
        self._arca = None
        for key, val in settings.items():
            if hasattr(self, key) and isinstance(getattr(self, key), LazySettingProperty) and val is not NOT_SET:
                setattr(self, key, val)

        self._current_hash = defaultdict(lambda: {})

    def inject_arca(self, arca):
        self._arca = arca

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

    def get_path_to_repo_base(self, repo: str) -> Path:
        return Path(self.base_dir) / self._arca.repo_id(repo)

    def get_path_to_repo(self, repo: str, branch: str) -> Path:
        return self.get_path_to_repo_base(repo).resolve() / branch

    def save_hash(self, repo: str, branch: str, git_repo: Repo):
        if self.single_pull:
            repo_id = self._arca.repo_id(repo)
            self._current_hash[repo_id][branch] = git_repo.head.object.hexsha

    def get_files(self, repo: str, branch: str) -> Tuple[Repo, Path]:
        repo_path = self.get_path_to_repo(repo, branch)

        logger.info("Repo is stored at %s", repo_path)

        if repo_path.exists():
            git_repo = Repo.init(repo_path)
            repo_id = self._arca.repo_id(repo)
            if not self.single_pull or self._current_hash[repo_id].get(branch) is None:
                logger.info("Single pull not enabled, no pull hasn't been done yet or pull forced, pulling")
                git_repo.remote().pull()
            else:
                logger.info("Single pull enabled and already pulled in this initialization of backend")
        else:
            repo_path.parent.mkdir(exist_ok=True, parents=True)
            logger.info("Initial pull")
            git_repo = Repo.clone_from(repo, str(repo_path), branch=branch, depth=1)

        self.save_hash(repo, branch, git_repo)

        return git_repo, repo_path

    def current_git_hash(self, repo: str, branch: str, short: bool=False) -> str:
        current_hash = self._current_hash[self._arca.repo_id(repo)].get(branch)

        if current_hash is not None:
            return current_hash

        git_repo, repo_path = self.get_files(repo, branch)

        if short:
            return git_repo.git.rev_parse(git_repo.head.object.hexsha, short=7)
        else:
            return git_repo.head.object.hexsha

    def static_filename(self, repo: str, branch: str, relative_path: Path) -> Path:
        _, repo_path = self.get_files(repo, branch)

        result = repo_path / relative_path

        logger.info("Static path for %s is %s", relative_path, result)

        return result

    def pull_again(self, repo: Optional[str]=None, branch: Optional[str]=None) -> None:
        if repo is None and branch is None:
            self._current_hash = {}
        elif repo is None:
            raise ValueError("You can't define just the branch to pull again.")  # TODO: custom exception
        elif branch is None:
            self._current_hash.pop(self._arca.repo_id(repo), None)
        else:
            repo_id = self._arca.repo_id(repo)
            self._current_hash[repo_id].pop(branch)

    def create_script(self, task: Task, venv_path: Path=None) -> Tuple[str, str]:
        script = task.build_script(venv_path)
        script_hash = hashlib.md5(bytes(script, "utf-8")).hexdigest()

        return f"{script_hash}.py", script

    def run(self, repo: str, branch: str, task: Task) -> Result:  # pragma: no cover
        raise NotImplementedError

    def create_environment(self, repo: str, branch: str):  # pragma: no cover
        raise NotImplementedError

    def update_environment(self, repo: str, branch: str):  # pragma: no cover
        raise NotImplementedError

    def environment_exists(self, repo: str, branch: str):  # pragma: no cover
        raise NotImplementedError
