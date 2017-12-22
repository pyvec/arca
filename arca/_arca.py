import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Union, Optional, Dict, Any, Tuple

import re
from dogpile.cache import make_region, CacheRegion
from git import Repo

from .backend import BaseBackend
from .result import Result
from .task import Task
from .utils import load_class, Settings, NOT_SET, logger, LazySettingProperty

BackendDefinitionType = Union[type, BaseBackend, str]


class Arca:

    single_pull: bool = LazySettingProperty(key="single_pull", default=False)
    base_dir: str = LazySettingProperty(key="base_dir", default=".arca")

    def __init__(self, backend: BackendDefinitionType=NOT_SET,
                 settings=None,
                 single_pull=None,
                 base_dir=None) -> None:
        self.settings: Settings = self._get_settings(settings)

        self.region: CacheRegion = self._make_region()

        self.backend: BaseBackend = self._get_backend_instance(backend)
        self.backend.inject_arca(self)

        self._current_hash = defaultdict(lambda: {})

        if single_pull is not None:
            self.single_pull = bool(single_pull)

        if base_dir is not None:
            self.base_dir = base_dir

    def _get_backend_instance(self, backend: BackendDefinitionType) -> BaseBackend:
        if backend is NOT_SET:
            backend = self.get_setting("backend", "arca.backend.VenvBackend")

        if isinstance(backend, str):
            backend = load_class(backend)

        if isinstance(backend, type):
            backend = backend()

        if not issubclass(backend.__class__, BaseBackend):
            raise ValueError(f"{backend.__class__} is not an subclass of BaseBackend")

        return backend

    def _get_settings(self, settings: Optional[Dict[str, Any]]) -> Settings:
        if settings is not None:
            _settings = Settings(settings)
        else:
            _settings = Settings()

        for key, val in os.environ.items():
            if key.startswith(Settings.PREFIX):
                _settings[key] = val

        return _settings

    def _make_region(self) -> CacheRegion:
        arguments = self.get_setting("cache_backend_arguments", None)

        if isinstance(arguments, str):
            arguments = json.loads(arguments)  # TODO: catch errors and raise custom exception

        return make_region().configure(
            self.get_setting("cache_backend", "dogpile.cache.null"),
            expiration_time=self.get_setting("cache_expiration_time", None),
            arguments=arguments
        )

    def validate_repo_url(self, repo: str):
        # that should match valid git repos
        if not isinstance(repo, str) or not re.match(r"^(https?|file)://[\w._\-/~]*[.git]?/?$", repo):
            # TODO: probably a custom exception would be better
            raise ValueError(f"{repo} is not a valid http[s] or file:// git repo")

    def repo_id(self, repo: str) -> str:
        if repo.startswith("http"):
            repo = re.sub(r"https?://(.www)?", "", repo)
            repo = re.sub(r"\.git/?$", "", repo)

            return "_".join(repo.split("/"))
        else:
            repo = repo.replace("file://", "")
            repo = re.sub(r"\.git/?$", "", repo)
            if repo.startswith("~"):
                repo = str(Path(repo).resolve())

            return "_".join(repo.split("/"))

    def get_setting(self, key: str, default=NOT_SET):
        return self.settings.get(key, default=default)

    def get_path_to_repo_base(self, repo: str) -> Path:
        return Path(self.base_dir) / self.repo_id(repo)

    def get_path_to_repo(self, repo: str, branch: str) -> Path:
        return self.get_path_to_repo_base(repo).resolve() / branch

    def save_hash(self, repo: str, branch: str, git_repo: Repo):
        if self.single_pull:
            repo_id = self.repo_id(repo)
            self._current_hash[repo_id][branch] = git_repo.head.object.hexsha

    def _pull(self, *, repo_path: Path=None, git_repo: Repo=None, repo: str=None, branch: str=None) -> Repo:
        """ A method which either pulls on a existing repo or creates a new repo based info.
            In a separate method so pulls can be counted in testing.
        """
        if git_repo is not None:
            git_repo.remote().pull()
            return git_repo
        else:
            return Repo.clone_from(repo, str(repo_path), branch=branch, depth=1)

    def current_git_hash(self, repo: str, branch: str, git_repo: Repo, short: bool=False) -> str:
        current_hash = self._current_hash[self.repo_id(repo)].get(branch)

        if current_hash is not None:
            return current_hash

        if short:
            return git_repo.git.rev_parse(git_repo.head.object.hexsha, short=7)
        else:
            return git_repo.head.object.hexsha

    def pull_again(self, repo: Optional[str]=None, branch: Optional[str]=None) -> None:
        if repo is None and branch is None:
            self._current_hash = {}
        elif repo is None:
            raise ValueError("You can't define just the branch to pull again.")  # TODO: custom exception
        elif branch is None and repo is not None:
            self._current_hash.pop(self.repo_id(repo), None)
        else:
            repo_id = self.repo_id(repo)
            try:
                self._current_hash[repo_id].pop(branch)
            except KeyError:
                pass

    def get_files(self, repo: str, branch: str) -> Tuple[Repo, Path]:
        repo_path = self.get_path_to_repo(repo, branch)

        logger.info("Repo is stored at %s", repo_path)

        if repo_path.exists():
            git_repo = Repo.init(repo_path)
            repo_id = self.repo_id(repo)
            if not self.single_pull or self._current_hash[repo_id].get(branch) is None:
                logger.info("Single pull not enabled, no pull hasn't been done yet or pull forced, pulling")
                self._pull(git_repo=git_repo)
            else:
                logger.info("Single pull enabled and already pulled in this initialization of backend")
        else:
            repo_path.parent.mkdir(exist_ok=True, parents=True)
            logger.info("Initial pull")
            git_repo = self._pull(repo_path=repo_path, repo=repo, branch=branch)

        self.save_hash(repo, branch, git_repo)

        return git_repo, repo_path

    def cache_key(self, repo: str, branch: str, task: Task, git_repo: Repo) -> str:
        return "{repo}_{branch}_{hash}_{task}".format(repo=self.repo_id(repo),
                                                      branch=branch,
                                                      hash=self.current_git_hash(repo, branch, git_repo),
                                                      task=task.serialize())

    def run(self, repo: str, branch: str, task: Task) -> Result:
        self.validate_repo_url(repo)

        logger.info("Running Arca task %r for repo '%s' in branch '%s'", task, repo, branch)

        git_repo, repo_path = self.get_files(repo, branch)

        def create_value():
            return self.backend.run(repo, branch, task, git_repo, repo_path)

        def should_cache(value: Result):
            return value.success

        return self.region.get_or_create(
            self.cache_key(repo, branch, task, git_repo),
            create_value,
            should_cache_fn=should_cache
        )

    def static_filename(self, repo: str, branch: str, relative_path: Union[str, Path]) -> Path:
        self.validate_repo_url(repo)

        if not isinstance(relative_path, Path):
            relative_path = Path(relative_path)

        _, repo_path = self.get_files(repo, branch)

        result = repo_path / relative_path

        logger.info("Static path for %s is %s", relative_path, result)

        return result
