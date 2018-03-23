# encoding=utf-8
import shutil
from datetime import datetime, timedelta, date
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

    with pytest.raises(ArcaMisconfigured):
        Arca("arca.backend_test.TestBackend")

    with pytest.raises(ArcaMisconfigured):
        Arca("arca.backend.TestBackend")

    class NotASubclassClass:
        pass

    with pytest.raises(ArcaMisconfigured):
        Arca(NotASubclassClass)


@pytest.mark.parametrize(["url", "valid"], [
    ("http://host.xz/path/to/repo.git/", True),
    ("https://host.xz/path/to/repo.git/", True),
    ("http://host.xz/path/to/repo.git", True),
    ("https://host.xz/path/to/repo.git", True),
    ("file:///path/to/repo.git/", True),
    ("file://~/path/to/repo.git/", True),
    ("http://host.xz/path/to/repo/", True),
    ("https://host.xz/path/to/repo/", True),
    ("http://host.xz/path/to/repo", True),
    ("https://host.xz/path/to/repo", True),
    ("file:///path/to/repo.git", True),
    ("file://~/path/to/repo.git", True),
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
])
def test_repo_id(url):
    backend = Arca()

    repo_id = backend.repo_id(url)

    assert "/" not in repo_id  # its a valid directory name
    # TODO: more checks?


@pytest.mark.parametrize("file_location", ["", "test_location"])
def test_static_files(temp_repo_static, file_location):
    arca = Arca(base_dir=BASE_DIR)

    filepath = temp_repo_static.fl
    if file_location:
        new_filepath = temp_repo_static.path / file_location / "test_file.txt"
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


def test_depth(temp_repo_static):
    arca = Arca(base_dir=BASE_DIR)

    for _ in range(19):  # since one commit is made in the fixture
        temp_repo_static.fl.write_text(str(uuid4()))
        temp_repo_static.repo.index.add([str(temp_repo_static.fl)])
        temp_repo_static.repo.index.commit("Initial")

    # test that in default settings, the whole repo is pulled in one go

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == 1  # default is 1

    # test when pulled again, the depth is increased since the local copy is stored

    temp_repo_static.fl.write_text(str(uuid4()))
    temp_repo_static.repo.index.add([str(temp_repo_static.fl)])
    temp_repo_static.repo.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == 2

    shutil.rmtree(str(cloned_repo_path))

    # test that when setting a certain depth, at least the depth is pulled (in case of merges etc)

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=10)
    assert cloned_repo.commit().count() >= 10
    before_second_pull = cloned_repo.commit().count()

    # test when pulled again, the depth setting is ignored

    temp_repo_static.fl.write_text(str(uuid4()))
    temp_repo_static.repo.index.add([str(temp_repo_static.fl)])
    temp_repo_static.repo.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch)
    assert cloned_repo.commit().count() == before_second_pull + 1

    shutil.rmtree(str(cloned_repo_path))

    # test when setting depth bigger than repo size, no fictional commits are included

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=100)

    assert cloned_repo.commit().count() == 22  # 20 plus the 2 extra commits

    shutil.rmtree(str(cloned_repo_path))

    # test no limit

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch, depth=-1)

    assert cloned_repo.commit().count() == 22  # 20 plus the 2 extra commits


@pytest.mark.parametrize("depth,valid", [
    (1, True),
    (5, True),
    ("5", True),
    (None, True),
    ("asddf", False),
    (-1, True),
    (0, False),
    (-2, False),
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

    git_dir_1 = Path("/tmp/arca/") / str(uuid4())
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

    cloned_repo, cloned_repo_path = arca.get_files(git_url_1, branch, reference=Path("/tmp/arca/") / str(uuid4()))
    assert (cloned_repo_path / "test_file.txt").read_text() == last_uuid
    shutil.rmtree(str(cloned_repo_path))

    # test existing reference with no common commits

    git_dir_2 = Path("/tmp/arca/") / str(uuid4())
    filepath_2 = git_dir_2 / "test_file.txt"
    repo_2 = Repo.init(git_dir_2)

    for _ in range(20):
        filepath_2.write_text(str(uuid4()))
        repo_2.index.add([str(filepath_2)])
        repo_2.index.commit("Initial")

    cloned_repo, cloned_repo_path = arca.get_files(git_url_1, branch, reference=git_dir_2)
    assert (cloned_repo_path / "test_file.txt").read_text() == last_uuid
    shutil.rmtree(str(cloned_repo_path))

    # test existing reference with common commits

    git_dir_3 = Path("/tmp/arca/") / str(uuid4())
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


def test_shallow_since(temp_repo_static):
    arca = Arca(base_dir=BASE_DIR)

    now = datetime.now()

    for i in range(19, 0, -1):
        temp_repo_static.fl.write_text(str(uuid4()))
        temp_repo_static.repo.index.add([str(temp_repo_static.fl)])
        temp_repo_static.repo.index.commit(
            "Initial",
            commit_date=(now - timedelta(days=i, hours=5)).strftime("%Y-%m-%dT%H:%M:%S"),
            author_date=(now - timedelta(days=i, hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
        )

    cloned_repo, cloned_repo_path = arca.get_files(temp_repo_static.url, temp_repo_static.branch,
                                                   shallow_since=(now - timedelta(days=10)).date())
    assert cloned_repo.commit().count() == 10


@pytest.mark.parametrize("shallow_since,valid", [
    (date(year=2018, month=1, day=1), True),
    ("2018-01-01", True),
    (datetime(year=2017, month=1, day=1), True),
    ("2018-01-01T01:00:00", False),
    ("sasdfasdf", False),
    (None, True)
])
def test_shallow_since_validate(temp_repo_static, shallow_since, valid):
    arca = Arca(base_dir=BASE_DIR)

    relative_path = Path("test_file.txt")

    if valid:
        arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path,
                             shallow_since=shallow_since)
    else:
        with pytest.raises(ValueError):
            arca.static_filename(temp_repo_static.url, temp_repo_static.branch, relative_path,
                                 shallow_since=shallow_since)


def test_pull_error():
    arca = Arca(base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())
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
