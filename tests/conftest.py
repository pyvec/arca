import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from collections import namedtuple

from git import Repo

from common import RETURN_STR_FUNCTION

TempRepo = namedtuple("TempRepo", ["repo", "path", "url", "branch", "fl"])


def create_temp_repo(fl) -> TempRepo:
    git_dir = Path(tempfile.mkdtemp())
    repo = Repo.init(str(git_dir))

    return TempRepo(repo, git_dir, f"file://{git_dir}", "master", git_dir / fl)


@pytest.fixture()
def temp_repo_func():
    temp_repo = create_temp_repo("test_file.py")

    temp_repo.fl.write_text(RETURN_STR_FUNCTION)

    temp_repo.repo.index.add([str(temp_repo.fl)])
    temp_repo.repo.index.commit("Initial")

    yield temp_repo

    shutil.rmtree(str(temp_repo.path))


@pytest.fixture()
def temp_repo_static():
    temp_repo = create_temp_repo("test_file.txt")

    temp_repo.fl.write_text("Some test file")

    temp_repo.repo.index.add([str(temp_repo.fl)])
    temp_repo.repo.index.commit("Initial")

    yield temp_repo

    shutil.rmtree(str(temp_repo.path))
