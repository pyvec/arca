# encoding=utf-8
import pytest
from git import Repo

from arca import Arca, VenvBackend
from arca.exceptions import ArcaMisconfigured


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
