import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Union, Optional, Dict, Any, Tuple, Callable

from dogpile.cache import make_region, CacheRegion
from git import Repo, GitCommandError

from .backend import BaseBackend
from .exceptions import ArcaMisconfigured, FileOutOfRangeError, PullError
from .result import Result
from .task import Task
from .utils import load_class, Settings, NOT_SET, logger, LazySettingProperty, NotSet

BackendDefinitionType = Union[Callable, BaseBackend, str, NotSet]
DepthDefinitionType = Optional[int]
ReferenceDefinitionType = Optional[Union[Path, str]]


class Arca:
    """ Basic interface for communicating with the library, most basic operations should be possible from this class.

    Available settings:

    * **base_dir**: Directory where cloned repositories and other files are stored (default: ``.arca``)
    * **single_pull**: Clone/pull each repository only once per initialization (default: ``False``)
    * **ignore_cache_errors**: Ignore all cache error initialization errors (default: ``False``)

    """

    base_dir: str = LazySettingProperty(default=".arca")
    single_pull: bool = LazySettingProperty(default=False, convert=bool)
    ignore_cache_errors: bool = LazySettingProperty(default=False, convert=bool)

    def __init__(self, backend: BackendDefinitionType=NOT_SET,
                 settings=None,
                 single_pull=NOT_SET,
                 base_dir=NOT_SET,
                 ignore_cache_errors=NOT_SET) -> None:
        self.settings: Settings = Settings(settings)

        if ignore_cache_errors is not NOT_SET:
            self.ignore_cache_errors = bool(ignore_cache_errors)

        if single_pull is not NOT_SET:
            self.single_pull = bool(single_pull)

        if base_dir is not NOT_SET:
            self.base_dir = base_dir

        self.region: CacheRegion = self.make_region()

        self.backend: BaseBackend = self.get_backend_instance(backend)
        self.backend.inject_arca(self)

        self._current_hashes: Dict[str, Dict[str, str]] = defaultdict(lambda: {})

    def get_backend_instance(self, backend: BackendDefinitionType) -> BaseBackend:
        """ Returns a backend instance, either from the argument or from the settings.

        :raise ArcaMisconfigured: If the instance is not a subclass of :class:`BaseBackend`
        """
        if backend is NOT_SET:
            backend = self.get_setting("backend", "arca.CurrentEnvironmentBackend")

        if isinstance(backend, str):
            backend = load_class(backend)

        if callable(backend):
            backend = backend()

        if not issubclass(type(backend), BaseBackend):
            raise ArcaMisconfigured(f"{type(backend)} is not an subclass of BaseBackend")

        return backend

    def make_region(self) -> CacheRegion:
        """
        Returns a :class:`CacheRegion <dogpile.cache.region.CacheRegion>` based on settings.

        * Firstly, a backend is selected.
          The default is :class:`NullBackend <dogpile.cache.backends.null.NullBackend`.
        * Secondly, arguments for the backends are generated.
          The arguments can be passed as a dict to the setting or as a json string.
          If the arguments aren't a dict or aren't convertible to a dict, :class:`ArcaMisconfigured` is raised.
        * Lastly, the cache is tested if it works

        All errors can be suppressed by the ``ignore_cache_errors`` setting.

        :raise ModuleNotFoundError: In case dogpile has trouble importing the library needed for a backend.
        :raise ArcaMisconfigured: In case the cache is misconfigured in any way or the cache doesn't work.
        """
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

        cache_backend = self.get_setting("cache_backend", "dogpile.cache.null")

        if cache_backend == "dogpile.cache.dbm":
            # if a file backend is used, create the folder for the file (if it doesn't exist)
            if isinstance(arguments, dict) and "filename" in arguments:
                Path(arguments["filename"]).parent.mkdir(parents=True, exist_ok=True)

        try:
            region = make_region().configure(
                cache_backend,
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
        """ Validates repo URL - if it's a valid git URL and if Arca can handle that type of repo URL

        :raise ValueError: If the URL is not valid
        """
        # that should match valid git repos
        if not isinstance(repo, str) or not re.match(r"^(https?|file)://[\w._\-/~]*[.git]?/?$", repo):
            raise ValueError(f"{repo} is not a valid http[s] or file:// git repository.")

    def repo_id(self, repo: str) -> str:
        """ Returns an unique identifier from a repo URL for the folder the repo is gonna be pulled in.
        """
        if repo.startswith("http"):
            repo_id = re.sub(r"https?://(.www)?", "", repo)
            repo_id = re.sub(r"\.git/?$", "", repo_id)
        else:
            repo_id = repo.replace("file://", "")
            repo_id = re.sub(r"\.git/?$", "", repo_id)
            if repo_id.startswith("~"):
                repo_id = str(Path(repo_id).resolve())

        # replaces everything that isn't alphanumeric, a dot or an underscore
        # to make sure it's a valid folder name and to keep it readable
        # multiple consecutive invalid characters replaced with a single underscore
        repo_id = re.sub(r"[^a-zA-Z0-9._]+", "_", repo_id)

        # and add a hash of the original to make it absolutely unique
        return repo_id + hashlib.sha256(repo.encode("utf-8")).hexdigest()

    def get_setting(self, key: str, default=NOT_SET):
        return self.settings.get(key, default=default)

    def get_path_to_repo(self, repo: str) -> Path:
        """ Returns a :class:`Path <pathlib.Path>` to the location where all the branches from this repo are stored.

        :param repo: Repo URL
        :return: Path to where branches from this repository are cloned.
        """
        return Path(self.base_dir) / "repos" / self.repo_id(repo)

    def get_path_to_repo_and_branch(self, repo: str, branch: str) -> Path:
        """ Returns a :class:`Path <pathlib.Path>` to where this specific branch is stored on disk.

        :param repo: Repo URL
        :param branch: branch
        :return: Path to where the specific branch from this repo is being cloned.
        """
        return self.get_path_to_repo(repo).resolve() / branch

    def save_hash(self, repo: str, branch: str, git_repo: Repo):
        """
        If ``single_pull`` is enabled, saves the current git hash of the specified repository/branch combination,
        to indicate that it shouldn't be pull again.
        """
        if self.single_pull:
            repo_id = self.repo_id(repo)
            self._current_hashes[repo_id][branch] = git_repo.head.object.hexsha

    def current_git_hash(self, repo: str, branch: str, git_repo: Repo, short: bool=False) -> str:
        """
        :param repo: Repo URL
        :param branch: Branch name
        :param git_repo: :class:`Repo <git.repo.base.Repo>` instance.
        :param short: Should the short version be returned?
        :return: Commit hash of the currently pulled version for the specified repo/branch
        """
        current_hash = self._current_hashes[self.repo_id(repo)].get(branch, git_repo.head.object.hexsha)

        if short:
            # shortens to minimum 7 characters, however git can make it longer on bigger repos
            return git_repo.git.rev_parse(current_hash, short=7)
        else:
            return current_hash

    def pull_again(self, repo: Optional[str]=None, branch: Optional[str]=None) -> None:
        """ When ``single_pull`` is enables, tells Arca to pull again.

        If ``repo`` and ``branch`` are not specified, pull again everything.

        :param repo: (Optional) Pull again all branches from a specified repository.
        :param branch: (Optional) When ``repo`` is specified, pull again only this branch from that repository.

        :raise ValueError: If ``branch`` is specified and ``repo`` is not.
        """
        if repo is None and branch is None:
            self._current_hashes = {}
        elif repo is None:
            raise ValueError("You can't define just the branch to pull again.")
        elif branch is None and repo is not None:
            self._current_hashes.pop(self.repo_id(repo), None)
        else:
            repo_id = self.repo_id(repo)
            try:
                self._current_hashes[repo_id].pop(branch)
            except KeyError:
                pass

    def get_reference_repository(self, reference: Optional[Path], repo: str) -> Optional[Path]:
        """
        Returns a repository to use in clone command, if there is one to be referenced.
        Either provided by the user of generated from already cloned branches (master is preferred).

        :param reference: Path to a local repository provided by the user or None.
        :param repo: Reference for which remote repository.
        """
        if reference is not None:
            return reference.absolute()

        repo_path = self.get_path_to_repo(repo)

        if not repo_path.exists():
            return None

        master = repo_path / "master"

        if master.exists() and master.is_dir():
            return master

        for existing_branch in repo_path.iterdir():
            if not existing_branch.is_dir():
                continue

            return existing_branch.resolve()

        return None

    def _pull(self, *, repo_path: Path=None, git_repo: Repo=None, repo: str=None, branch: str=None,
              depth: Optional[int]=None,
              reference: Optional[Path]=None
              ) -> Repo:
        """
        Returns a :class:`Repo <git.repo.base.Repo>` instance, either pulls existing or
        clones a new copy.
        """
        if git_repo is not None:
            try:
                git_repo.remote().fetch(branch)
                # equivalent to git reset --hard origin/branch
                git_repo.head.reset(f"origin/{branch}", index=True, working_tree=True)
            except GitCommandError:
                raise PullError("There was an error pulling the target repository.")
            return git_repo
        else:
            kwargs: Dict[str, Any] = {}

            if depth is not None:
                kwargs["depth"] = depth

            reference = self.get_reference_repository(reference, repo)

            if reference is not None:
                kwargs["reference-if-able"] = str(reference)
                kwargs["dissociate"] = True

            try:
                return Repo.clone_from(repo, str(repo_path), branch=branch, **kwargs)
            except GitCommandError:
                raise PullError("There was an error cloning the target repository.")

    def get_files(self, repo: str, branch: str, *,
                  depth: Optional[int]=1,
                  reference: Optional[Path]=None
                  ) -> Tuple[Repo, Path]:
        """
        Either clones the repository if it's not cloned already or pulls from origin.
        If ``single_pull`` is enabled, only pulls if the repo/branch combination wasn't pulled again by this instance.

        :param repo: Repo URL
        :param branch: Branch name
        :param depth:  See :meth:`run`
        :param reference: See :meth:`run`

        :return: A :class:`Repo <git.repo.base.Repo>` instance for the repo
                 and a :class:`Path <pathlib.Path>` to the location where the repo is stored.
        """
        repo_path = self.get_path_to_repo_and_branch(repo, branch)

        logger.info("Repo is stored at %s", repo_path)

        if repo_path.exists():
            git_repo = Repo.init(repo_path)
            repo_id = self.repo_id(repo)
            if not self.single_pull or self._current_hashes[repo_id].get(branch) is None:
                logger.info("Single pull not enabled, no pull hasn't been done yet or pull forced, pulling")
                self._pull(git_repo=git_repo, branch=branch)
            else:
                logger.info("Single pull enabled and already pulled in this initialization of backend")
        else:
            repo_path.parent.mkdir(exist_ok=True, parents=True)
            logger.info("Initial pull")
            git_repo = self._pull(repo_path=repo_path, repo=repo, branch=branch,
                                  depth=depth,
                                  reference=reference)

        self.save_hash(repo, branch, git_repo)

        return git_repo, repo_path

    def get_repo(self, repo: str, branch: str, *,
                 depth: Optional[int]=1,
                 reference: Optional[Path]=None
                 ) -> Repo:
        """ Returns a :class:`Repo <git.repo.base.Repo>` instance for the branch.

        See :meth:`run` for arguments descriptions.
        """
        git_repo, _ = self.get_files(repo, branch, depth=depth, reference=reference)

        return git_repo

    def cache_key(self, repo: str, branch: str, task: Task, git_repo: Repo) -> str:
        """ Returns the key used for storing results in cache.
        """
        return "{repo}_{branch}_{hash}_{task}".format(repo=self.repo_id(repo),
                                                      branch=branch,
                                                      hash=self.current_git_hash(repo, branch, git_repo),
                                                      task=task.hash)

    def run(self, repo: str, branch: str, task: Task, *,
            depth: DepthDefinitionType=1,
            reference: ReferenceDefinitionType=None
            ) -> Result:
        """ Runs the ``task`` using the configured backend.

        :param repo: Target git repository
        :param branch: Target git branch
        :param task: Task which will be run in the target repository
        :param depth: How many commits back should the repo be cloned in case the target repository isn't cloned yet.
                      Defaults to 1, must be bigger than 0. No limit will be used if ``None`` is set.
        :param reference: A path to a repository from which the target repository is forked,
                          to save bandwidth, `--dissociate` is used if set.

        :return: A :class:`Result` instance with the output of the task.

        :raise PullError: If the repository can't be cloned or pulled
        :raise BuildError: If the task fails.
        """
        self.validate_repo_url(repo)
        depth = self.validate_depth(depth)
        reference = self.validate_reference(reference)

        logger.info("Running Arca task %r for repo '%s' in branch '%s'", task, repo, branch)

        git_repo, repo_path = self.get_files(repo, branch, depth=depth, reference=reference)

        def create_value():
            logger.debug("Value not in cache, creating.")
            return self.backend.run(repo, branch, task, git_repo, repo_path)

        cache_key = self.cache_key(repo, branch, task, git_repo)

        logger.debug("Cache key is %s", cache_key)

        return self.region.get_or_create(
            cache_key,
            create_value,
            should_cache_fn=self.should_cache_fn
        )

    def should_cache_fn(self, value: Result) -> bool:
        """
        Returns if the result ``value`` should be cached. By default, always returns ``True``, can be
        overriden.
        """
        return True

    def static_filename(self, repo: str, branch: str, relative_path: Union[str, Path], *,
                        depth: DepthDefinitionType=1,
                        reference: ReferenceDefinitionType=None
                        ) -> Path:
        """
        Returns an absolute path to where a file from the repo was cloned to.

        :param repo: Repo URL
        :param branch: Branch name
        :param relative_path: Relative path to the requested file
        :param depth: See :meth:`run`
        :param reference: See :meth:`run`

        :return: Absolute path to the file in the target repository

        :raise FileOutOfRangeError: If the relative path leads out of the repository path
        :raise FileNotFoundError: If the file doesn't exist in the repository.
        """
        self.validate_repo_url(repo)
        depth = self.validate_depth(depth)
        reference = self.validate_reference(reference)

        if not isinstance(relative_path, Path):
            relative_path = Path(relative_path)

        _, repo_path = self.get_files(repo, branch, depth=depth, reference=reference)

        result = repo_path / relative_path
        result = result.resolve()

        if repo_path not in result.parents:
            raise FileOutOfRangeError(f"{relative_path} is not inside the repository.")

        if not result.exists():
            raise FileNotFoundError(f"{relative_path} does not exist in the repository.")

        logger.info("Static path for %s is %s", relative_path, result)

        return result

    def validate_depth(self, depth: DepthDefinitionType) -> Optional[int]:
        """ Converts the depth to int and validates that the value can be used.

        :raise ValueError: If the provided depth is not valid
        """
        if depth is not None:
            try:
                depth = int(depth)
            except ValueError:
                raise ValueError(f"Depth '{depth}' can't be converted to int.")

            if depth < 1:
                raise ValueError(f"Depth '{depth}' isn't a positive number")

            return depth
        return None

    def validate_reference(self, reference: ReferenceDefinitionType) -> Optional[Path]:
        """ Converts reference to :class:`Path <pathlib.Path>`

        :raise ValueError: If ``reference`` can't be converted to :class:`Path <pathlib.Path>`.
        """
        if reference is not None:
            if isinstance(reference, bytes):
                reference = reference.decode("utf-8")
            try:
                return Path(reference)
            except TypeError:
                raise ValueError(f"Can't convert reference path {reference} to a pathlib.Path")

        return None
