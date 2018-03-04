import json
import os
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Union, Optional, Dict, Any, Tuple

import re
from dogpile.cache import make_region, CacheRegion
from git import Repo, InvalidGitRepositoryError, GitCommandError

from .exceptions import ArcaMisconfigured, FileOutOfRangeError, PullError
from .backend import BaseBackend
from .result import Result
from .task import Task
from .utils import load_class, Settings, NOT_SET, logger, LazySettingProperty

BackendDefinitionType = Union[type, BaseBackend, str]
DepthDefinitionType = Optional[int]
ShallowSinceDefinitionType = Optional[Union[str, date]]
ReferenceDefinitionType = Optional[Union[Path, str]]


class Arca:

    single_pull: bool = LazySettingProperty(key="single_pull", default=False, convert=bool)
    base_dir: str = LazySettingProperty(key="base_dir", default=".arca")
    ignore_cache_errors: bool = LazySettingProperty(key="ignore_cache_errors", default=False, convert=bool)

    def __init__(self, backend: BackendDefinitionType=NOT_SET,
                 settings=None,
                 single_pull=None,
                 base_dir=None,
                 ignore_cache_errors=None) -> None:
        self.settings: Settings = self._get_settings(settings)

        if ignore_cache_errors is not None:
            self.ignore_cache_errors = bool(ignore_cache_errors)

        if single_pull is not None:
            self.single_pull = bool(single_pull)

        if base_dir is not None:
            self.base_dir = base_dir

        self.region: CacheRegion = self._make_region()

        self.backend: BaseBackend = self._get_backend_instance(backend)
        self.backend.inject_arca(self)

        self._current_hash: Dict[str, Dict[str, str]] = defaultdict(lambda: {})

    def _get_backend_instance(self, backend: BackendDefinitionType) -> BaseBackend:
        if backend is NOT_SET:
            backend = self.get_setting("backend", "arca.backend.CurrentEnvironmentBackend")

        if isinstance(backend, str):
            backend = load_class(backend)

        if isinstance(backend, type):
            backend = backend()

        if not issubclass(backend.__class__, BaseBackend):
            raise ArcaMisconfigured(f"{backend.__class__} is not an subclass of BaseBackend")

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

        def null_cache():
            return make_region().configure(
                "dogpile.cache.null"
            )

        if isinstance(arguments, str) and arguments:
            try:
                arguments = json.loads(arguments)
            except ValueError:
                if self.ignore_cache_errors:
                    return null_cache()
                raise ArcaMisconfigured("Cache backend arguments couldn't be converted to a dictionary.")

        try:
            region = make_region().configure(
                self.get_setting("cache_backend", "dogpile.cache.null"),
                expiration_time=self.get_setting("cache_expiration_time", None),
                arguments=arguments
            )
            region.set("last_arca_run", datetime.now().isoformat())
        except ModuleNotFoundError:
            if self.ignore_cache_errors:
                return null_cache()
            raise ModuleNotFoundError("Cache backend cannot load a required library.")
        except Exception:
            if self.ignore_cache_errors:
                return null_cache()
            raise ArcaMisconfigured("The provided cache is not working - most likely misconfigured.")

        return region

    def validate_repo_url(self, repo: str):
        # that should match valid git repos
        if not isinstance(repo, str) or not re.match(r"^(https?|file)://[\w._\-/~]*[.git]?/?$", repo):
            raise ValueError(f"{repo} is not a valid http[s] or file:// git repository.")

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
        return Path(self.base_dir) / "repos" / self.repo_id(repo)

    def get_path_to_repo(self, repo: str, branch: str) -> Path:
        return self.get_path_to_repo_base(repo).resolve() / branch

    def save_hash(self, repo: str, branch: str, git_repo: Repo):
        if self.single_pull:
            repo_id = self.repo_id(repo)
            self._current_hash[repo_id][branch] = git_repo.head.object.hexsha

    def _pull(self, *, repo_path: Path=None, git_repo: Repo=None, repo: str=None, branch: str=None,
              depth: Optional[int] = None,
              shallow_since: Optional[date] = None,
              reference: Optional[Path] = None
              ) -> Repo:
        """ A method which either pulls on a existing repo or creates a new repo based info.
            In a separate method so pulls can be counted in testing.
        """
        if git_repo is not None:
            try:
                git_repo.remote().pull()
            except GitCommandError:
                raise PullError("There was an error pulling the target repository.")
            return git_repo
        else:
            kwargs = {}

            if shallow_since is None:
                if depth != -1:
                    kwargs["depth"] = depth or 1
            else:
                kwargs["shallow-since"] = (shallow_since - timedelta(days=1)).strftime("%Y-%m-%d")

            if reference is not None:
                kwargs["reference-if-able"] = str(reference.absolute())
                kwargs["dissociate"] = True

            try:
                return Repo.clone_from(repo, str(repo_path), branch=branch, **kwargs)
            except GitCommandError:
                raise PullError("There was an error cloning the target repository.")

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
            raise ValueError("You can't define just the branch to pull again.")
        elif branch is None and repo is not None:
            self._current_hash.pop(self.repo_id(repo), None)
        else:
            repo_id = self.repo_id(repo)
            try:
                self._current_hash[repo_id].pop(branch)
            except KeyError:
                pass

    def get_files(self, repo: str, branch: str, *,
                  depth: Optional[int] = None,
                  shallow_since: Optional[date] = None,
                  reference: Optional[Path] = None
                  ) -> Tuple[Repo, Path]:
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
            git_repo = self._pull(repo_path=repo_path, repo=repo, branch=branch,
                                  depth=depth,
                                  shallow_since=shallow_since,
                                  reference=reference)

        self.save_hash(repo, branch, git_repo)

        return git_repo, repo_path

    def cache_key(self, repo: str, branch: str, task: Task, git_repo: Repo) -> str:
        return "{repo}_{branch}_{hash}_{task}".format(repo=self.repo_id(repo),
                                                      branch=branch,
                                                      hash=self.current_git_hash(repo, branch, git_repo),
                                                      task=task.serialize())

    def is_dirty(self) -> bool:
        """ Returns if the repository the code is launched from was modified in any way.
            Returns False if not in a repository.
        """
        try:
            return Repo(".", search_parent_directories=True).is_dirty(untracked_files=True)
        except InvalidGitRepositoryError:
            return False

    def run(self, repo: str, branch: str, task: Task, *,
            depth: DepthDefinitionType=None,
            shallow_since: ShallowSinceDefinitionType=None,
            reference: ReferenceDefinitionType=None
            ) -> Result:
        """
        :param repo: Target git repository
        :param branch: Target git branch
        :param task: Task which will be run in the target repository
        :param depth: How many commits back should the repo be cloned in case the target repository isn't cloned yet.
                      Defaults to 1, ignored if `shallow_since` is set. -1 means no limit, otherwise must be positive.
        :param shallow_since: Shallow clone in case the target repository isn't cloned yet, including the date.
        :param reference: A path to a repository from which the target repository is forked,
                          to save bandwidth, `--dissociate` is used if set.
        """
        self.validate_repo_url(repo)
        depth = self.validate_depth(depth)
        shallow_since = self.validate_shallow_since(shallow_since)
        reference = self.validate_reference(reference)

        logger.info("Running Arca task %r for repo '%s' in branch '%s'", task, repo, branch)

        git_repo, repo_path = self.get_files(repo, branch,
                                             depth=depth,
                                             shallow_since=shallow_since,
                                             reference=reference)

        def create_value():
            return self.backend.run(repo, branch, task, git_repo, repo_path)

        return self.region.get_or_create(
            self.cache_key(repo, branch, task, git_repo),
            create_value,
            should_cache_fn=self.should_cache_fn
        )

    def should_cache_fn(self, value: Result) -> bool:
        """ Can be overridden to designate if dogpile should or shouldn't cache this value.
        """
        return True

    def static_filename(self, repo: str, branch: str, relative_path: Union[str, Path],
                        depth: DepthDefinitionType = None,
                        shallow_since: ShallowSinceDefinitionType = None,
                        reference: ReferenceDefinitionType = None
                        ) -> Path:
        self.validate_repo_url(repo)
        depth = self.validate_depth(depth)
        shallow_since = self.validate_shallow_since(shallow_since)
        reference = self.validate_reference(reference)

        if not isinstance(relative_path, Path):
            relative_path = Path(relative_path)

        _, repo_path = self.get_files(repo, branch,
                                      depth=depth,
                                      shallow_since=shallow_since,
                                      reference=reference)

        result = repo_path / relative_path
        result = result.resolve()

        if repo_path not in result.parents:
            raise FileOutOfRangeError(f"{relative_path} is not inside the repository.")

        if not result.exists():
            raise FileNotFoundError(f"{relative_path} does not exist in the repository.")

        logger.info("Static path for %s is %s", relative_path, result)

        return result

    def validate_depth(self, depth: DepthDefinitionType) -> Optional[int]:
        if depth is not None:
            try:
                depth = int(depth)
            except ValueError:
                raise ValueError("Depth '{}' can't be converted to int.".format(depth))

            if not (depth == -1 or depth > 0):
                raise ValueError("Depth '{}' isn't positive or -1 to indicate no limit".format(depth))
            return depth
        return None

    def validate_shallow_since(self, shallow_since: ShallowSinceDefinitionType) -> Optional[date]:
        if shallow_since is not None:
            if isinstance(shallow_since, datetime):
                return shallow_since.date()
            elif isinstance(shallow_since, date):
                return shallow_since
            try:
                return datetime.strptime(shallow_since, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Shallows since value '{}' isn't a date or a string in format "
                                 "YYYY-MM-DD".format(shallow_since))

        return None

    def validate_reference(self, reference: ReferenceDefinitionType) -> Optional[Path]:
        if reference is not None:
            if isinstance(reference, bytes):
                reference = reference.decode("utf-8")
            try:
                return Path(reference)
            except TypeError:
                raise ValueError("Can't convert reference path to a pathlib.Path")

        return None
