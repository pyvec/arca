import shutil
import tempfile
from pathlib import Path

import pytest
from collections import namedtuple

from git import Repo

from common import RETURN_STR_FUNCTION

TempRepo = namedtuple("TempRepo", ["repo", "repo_path", "url", "branch", "file_path"])


def create_temp_repo(file) -> TempRepo:
    git_dir = Path(tempfile.mkdtemp())
    repo = Repo.init(str(git_dir))

    return TempRepo(
        repo, git_dir, f"file://{git_dir}", "master", git_dir / file,
    )


@pytest.fixture(params=["master", "branch/with/slash"])
def temp_repo_func(request):
    temp_repo = create_temp_repo("test_file.py")

    temp_repo.file_path.write_text(RETURN_STR_FUNCTION)

    temp_repo.repo.index.add([str(temp_repo.file_path)])
    temp_repo.repo.index.commit("Initial")

    branch_name = request.param
    if branch_name != "master":
        # Now that there is a commit, create a branch
        temp_repo = temp_repo._replace(branch=branch_name)
        branch = temp_repo.repo.create_head(branch_name)
        temp_repo.repo.head.reference = branch

    yield temp_repo

    shutil.rmtree(str(temp_repo.repo_path))


@pytest.fixture()
def temp_repo_static():
    temp_repo = create_temp_repo("test_file.txt")

    temp_repo.file_path.write_text("Some test file")

    temp_repo.repo.index.add([str(temp_repo.file_path)])
    temp_repo.repo.index.commit("Initial")

    yield temp_repo

    shutil.rmtree(str(temp_repo.repo_path))
