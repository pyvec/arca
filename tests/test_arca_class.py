# encoding=utf-8
import os
import platform
import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from git import Repo

from arca import Arca, VenvBackend
from arca.exceptions import ArcaMisconfigured, FileOutOfRangeError, PullError
from common import BASE_DIR


def test_arca_backend():
    assert isinstance(Arca(VenvBackend()).backend, VenvBackend)
    assert isinstance(Arca(VenvBackend).backend, VenvBackend)
    assert isinstance(Arca("arca.backend.VenvBackend").backend, VenvBackend)
    assert isinstance(Arca(lambda: VenvBackend()).backend, VenvBackend)

    with pytest.raises(ArcaMisconfigured):
        Arca("arca.backend_test.TestBackend")

    with pytest.raises(ArcaMisconfigured):
        Arca("arca.backend.TestBackend")

    class NotASubclassClass:
        pass

    with pytest.raises(ArcaMisconfigured):
        Arca(NotASubclassClass)


@pytest.mark.parametrize(["url", "valid"], [
    # http/s
    ("http://host.xz/path/to/repo.git/", True),
    ("https://host.xz/path/to/repo.git/", True),
    ("http://host.xz/path/to/repo.git", True),
    ("https://host.xz/path/to/repo.git", True),
    ("http://host.xz/path/to/repo/", True),
    ("https://host.xz/path/to/repo/", True),
    ("http://host.xz/path/to/repo", True),
    ("https://host.xz/path/to/repo", True),

    # linux paths
    pytest.param("file:///path/to/repo.git/", True,
                 marks=pytest.mark.skipif(platform.system() == "Windows", reason="Linux Path")),
    pytest.param("file://~/path/to/repo.git/", True,
                 marks=pytest.mark.skipif(platform.system() == "Windows", reason="Linux Path")),
    pytest.param("file:///path/to/repo.git", True,
                 marks=pytest.mark.skipif(platform.system() == "Windows", reason="Linux Path")),
    pytest.param("file://~/path/to/repo.git", True,
                 marks=pytest.mark.skipif(platform.system() == "Windows", reason="Linux Path")),

    # windows paths
    pytest.param("file:///C:\\user\\path \\to\\repo", True,
                 marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows Path")),
    pytest.param("file:///c:\\user\\path \\to\\repo", True,
                 marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows Path")),

    # ssh
    ("git://host.xz/path/to/repo.git/", False),
    ("git://host.xz/~user/path/to/repo.git/", False),
    ("ssh://host.xz/path/to/repo.git/", False),
    (1, False),
    (Repo(), False),
])
def test_validate_repo_url(url, valid):
    arca = Arca()

    if valid:
        arca.validate_repo_url(url)
    else:
        with pytest.raises(ValueError):
            arca.validate_repo_url(url)


@pytest.mark.parametrize("url", [
    "http://host.xz/path/to/repo.git/",
    "https://host.xz/path/to/repo.git/",
    "http://host.xz/path/to/repo.git",
    "https://host.xz/path/to/repo.git",
    "file:///path/to/repo.git/",
    "file://~/path/to/repo.git/",
    "http://host.xz/path/to/repo/",
    "https://host.xz/path/to/repo/",
    "http://host.xz/path/to/repo",
    "https://host.xz/path/to/repo",
    "file:///path/to/repo.git",
    "file://~/path/to/repo.git",
    "https://host.xz/path/to/repo///with///a//lot/of/slashes/git/",
    "https://host.xz/path/to/repo_with   spaces.git/",
    "https://host.xz/path/to/repo_with_úňíčóďé_characters.git/",
])
def test_repo_id(url):
    arca = Arca()

    repo_id = arca.repo_id(url)

    # it's a valid folder name with only alphanumeric, dot or underscore characters
    assert re.match(r"^[a-zA-Z0-9._]+$", repo_id)


def test_repo_id_unique():
    arca = Arca()

    repo_id_1 = arca.repo_id("http://github.com/pyvec/naucse.python.cz")
    repo_id_2 = arca.repo_id("http://github.com_pyvec_naucse.python.cz")

    assert repo_id_1 != repo_id_2


@pytest.mark.parametrize("file_location", ["", "test_location"])
def test_static_files(temp_repo_static, file_location):
    arca = Arca(base_dir=BASE_DIR)

    filepath = temp_repo_static.file_path
    if file_location:
        new_filepath = temp_repo_static.repo_path / file_location / "test_file.txt"
        new_filepath.parent.mkdir(exist_ok=True, parents=True)

        filepath.replace(new_filepath)

        temp_repo_static.repo.index.add([str(new_filepath)])
        temp_repo_static.repo.index.remove([str(filepath)])
        temp_repo_static.repo.index.commit("Initial")

        filepath = new_filepath

    relative_path = Path(file_location) / "test_file.txt"
    nonexistent_relative_path = Path(file_location) / "test_file2.txt"

    result = arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path)

    assert filepath.read_text() == result.read_text()

    result = arca.static_filename(temp_repo_static.url, temp_repo_static.branch, str(relative_path))

    assert filepath.read_text() == result.read_text()

    with pytest.raises(FileOutOfRangeError):
        arca.static_filename(temp_repo_static.url, temp_repo_static.branch, "../file.txt")

    with pytest.raises(FileNotFoundError):
        arca.static_filename(temp_repo_static.url, temp_repo_static.branch, nonexistent_relative_path)


def test_current_git_hash(temp_repo_static):
    """
    Test that the :meth:`Arca.current_git_hash <arca.Arca.current_git_hash>` behaves the same when ``single_pull``
    is disabled or enabled.
    """
    arca = Arca(base_dir=BASE_DIR)
    repo, _ = arca.get_files(temp_repo_static.url, temp_repo_static.branch)

    long_hash = arca.current_git_hash(temp_repo_static.url, temp_repo_static.branch, repo)
    short_hash = arca.current_git_hash(temp_repo_static.url, temp_repo_static.branch, repo, short=True)

    assert len(short_hash) < len(long_hash)
    assert long_hash.startswith(short_hash)

    arca = Arca(base_dir=BASE_DIR, single_pull=True)

    repo, _ = arca.get_files(temp_repo_static.url, temp_repo_static.branch)

    long_hash_single_pull = arca.current_git_hash(temp_repo_static.url, temp_repo_static.branch, repo)
    short_hash_single_pull = arca.current_git_hash(temp_repo_static.url, temp_repo_static.branch, repo, short=True)

    assert long_hash == long_hash_single_pull
    assert short_hash == short_hash_single_pull


def test_depth(temp_repo_static):
    arca = Arca(base_dir=BASE_DIR)

    for _ in range(19):  # since one commit is made in the fixture
        temp_repo_static.file_path.write_text(str(uuid4()))
        temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
        temp_repo_static.repo.index.commit("Initial")

    # test that in default settings, the whole repo is pulled in one go

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == 1  # default is 1

    # test when pulled again, the depth is increased since the local copy is stored

    temp_repo_static.file_path.write_text(str(uuid4()))
    temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
    temp_repo_static.repo.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == 2

    if not os.environ.get("APPVEYOR", False):
        shutil.rmtree(str(cloned_repo_path))

    # test that when setting a certain depth, at least the depth is pulled (in case of merges etc)

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=10)
    assert cloned_repo.commit().count() >= 10
    before_second_pull = cloned_repo.commit().count()

    # test when pulled again, the depth setting is ignored

    temp_repo_static.file_path.write_text(str(uuid4()))
    temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
    temp_repo_static.repo.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == before_second_pull + 1

    if not os.environ.get("APPVEYOR", False):
        shutil.rmtree(str(cloned_repo_path))

    # test when setting depth bigger than repo size, no fictional commits are included

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=100)

    assert cloned_repo.commit().count() == 22  # 20 plus the 2 extra commits

    if not os.environ.get("APPVEYOR", False):
        shutil.rmtree(str(cloned_repo_path))

    # test no limit

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=None)

    assert cloned_repo.commit().count() == 22  # 20 plus the 2 extra commits


@pytest.mark.parametrize("depth,valid", [
    (1, True),
    (5, True),
    ("5", True),
    (None, True),
    ("asddf", False),
    (-1, False),
    (-2, False),
    (0, False),
])
def test_depth_validate(temp_repo_static, depth, valid):
    arca = Arca(base_dir=BASE_DIR)

    relative_path = Path("test_file.txt")

    if valid:
        arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path, depth=depth)
    else:
        with pytest.raises(ValueError):
            arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path, depth=depth)


def test_reference():
    arca = Arca(base_dir=BASE_DIR)
    branch = "master"

    git_dir_1 = Path(BASE_DIR) / str(uuid4())
    git_url_1 = f"file://{git_dir_1}"
    filepath_1 = git_dir_1 / "test_file.txt"
    repo_1 = Repo.init(git_dir_1)

    last_uuid = None

    for _ in range(20):
        last_uuid = str(uuid4())
        filepath_1.write_text(last_uuid)
        repo_1.index.add([str(filepath_1)])
        repo_1.index.commit("Initial")

    # test nonexistent reference

    cloned_repo, cloned_repo_path = arca.get_files(git_url_1, branch, reference=Path(BASE_DIR) / str(uuid4()))
    assert (cloned_repo_path / "test_file.txt").read_text() == last_uuid

    if not os.environ.get("APPVEYOR", False):
        shutil.rmtree(str(cloned_repo_path))

    # test existing reference with no common commits

    git_dir_2 = Path(BASE_DIR) / str(uuid4())
    filepath_2 = git_dir_2 / "test_file.txt"
    repo_2 = Repo.init(git_dir_2)

    for _ in range(20):
        filepath_2.write_text(str(uuid4()))
        repo_2.index.add([str(filepath_2)])
        repo_2.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(git_url_1, branch, reference=git_dir_2)
    assert (cloned_repo_path / "test_file.txt").read_text() == last_uuid

    if not os.environ.get("APPVEYOR", False):
        shutil.rmtree(str(cloned_repo_path))

    # test existing reference with common commits

    git_dir_3 = Path(BASE_DIR) / str(uuid4())
    git_url_3 = f"file://{git_dir_3}"
    filepath_3 = git_dir_3 / "test_file.txt"
    repo_3 = repo_1.clone(str(git_dir_3))  # must pass string, fails otherwise

    for _ in range(20):
        last_uuid = str(uuid4())
        filepath_3.write_text(last_uuid)
        repo_3.index.add([str(filepath_3)])
        repo_3.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(git_url_3, branch, reference=git_dir_1)
    assert (cloned_repo_path / "test_file.txt").read_text() == last_uuid


@pytest.mark.parametrize("reference,valid", [
    ("/tmp/" + str(uuid4()), True),
    (b"/tmp/" + str(uuid4()).encode("utf-8"), True),
    (Path("/tmp/") / str(uuid4()), True),
    (None, True),
    (1, False)
])
def test_reference_validate(temp_repo_static, reference, valid):
    arca = Arca(base_dir=BASE_DIR)

    relative_path = Path("test_file.txt")

    if valid:
        arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path, reference=reference)
    else:
        with pytest.raises(ValueError):
            arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path, reference=reference)


def test_get_reference_repository(temp_repo_static):
    """
    Test that the :meth:`Arca.get_reference_repository` works when reference is not provided by the user
    or when branch `master` is not pulled first (as it is in other tests).
    """
    temp_repo_static.file_path.write_text("master")
    temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
    temp_repo_static.repo.index.commit("Initial")

    for branch in "branch1", "branch2", "branch3":
        temp_repo_static.repo.create_head(branch)
        temp_repo_static.repo.branches[branch].checkout()
        temp_repo_static.file_path.write_text(branch)
        temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
        temp_repo_static.repo.index.commit(branch)

    arca = Arca(base_dir=BASE_DIR)

    for branch in "branch1", "branch2", "master", "branch3":
        _, path = arca.get_files(temp_repo_static.url, branch)

        assert (path / temp_repo_static.file_path.name).read_text() == branch


def test_pull_error():
    arca = Arca(base_dir=BASE_DIR)

    git_dir = Path(BASE_DIR) / str(uuid4())
    git_url = f"file://{git_dir}"

    with pytest.raises(PullError):
        arca.get_files(git_url, "master")

    filepath = git_dir / "test_file.txt"
    repo = Repo.init(git_dir)
    filepath.write_text(str(uuid4()))
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    arca.get_files(git_url, "master")

    with pytest.raises(PullError):
        arca.get_files(git_url, "some_branch")

    shutil.rmtree(str(git_dir))

    with pytest.raises(PullError):
        arca.get_files(git_url, "master")


def test_get_repo(temp_repo_static):
    arca = Arca(base_dir=BASE_DIR)

    pulled_repo = arca.get_repo(temp_repo_static.url, temp_repo_static.branch)

    assert pulled_repo.head.object.hexsha == temp_repo_static.repo.head.object.hexsha


def test_fetch_and_reset(temp_repo_static):
    """
    Tests updating already cloned repo, which was rebased.
    Prevents ``fatal: refusing to merge unrelated histories``.
    """
    arca = Arca(base_dir=BASE_DIR)

    initial_value = str(uuid4())
    temp_repo_static.file_path.write_text(initial_value)
    temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
    temp_repo_static.repo.index.commit("Update")
    initial_commit = temp_repo_static.repo.head.object.hexsha

    for _ in range(5):
        temp_repo_static.file_path.write_text(str(uuid4()))
        temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
        temp_repo_static.repo.index.commit("Update")

    arca.get_files(temp_repo_static.url, temp_repo_static.branch)

    temp_repo_static.repo.head.reset(initial_commit)

    _, path_to_cloned = arca.get_files(temp_repo_static.url, temp_repo_static.branch)

    assert (path_to_cloned / temp_repo_static.file_path.name).read_text() == initial_value
