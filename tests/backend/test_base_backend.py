import pytest
from git import Repo

from arca.backend.base import BaseBackend


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
    backend = BaseBackend()

    if valid:
        backend.validate_repo_url(url)
    else:
        with pytest.raises(ValueError):
            backend.validate_repo_url(url)


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
    backend = BaseBackend()

    repo_id = backend.repo_id(url)

    assert "/" not in repo_id  # its a valid directory name
    # TODO: more checks?
