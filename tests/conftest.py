import platform
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

    file_url = f"file://{git_dir}"

    if platform.system() == "Windows":
        file_url = f"file:///{git_dir}"

    return TempRepo(repo, git_dir, file_url, "master", git_dir / file)


@pytest.fixture()
def temp_repo_func():
    temp_repo = create_temp_repo("test_file.py")

    temp_repo.file_path.write_text(RETURN_STR_FUNCTION)

    temp_repo.repo.index.add([str(temp_repo.file_path)])
    temp_repo.repo.index.commit("Initial")

    yield temp_repo

    temp_repo.repo.close()
    shutil.rmtree(str(temp_repo.repo_path))


@pytest.fixture()
def temp_repo_static():
    temp_repo = create_temp_repo("test_file.txt")

    temp_repo.file_path.write_text("Some test file")

    temp_repo.repo.index.add([str(temp_repo.file_path)])
    temp_repo.repo.index.commit("Initial")

    yield temp_repo

    temp_repo.repo.close()
    shutil.rmtree(str(temp_repo.repo_path))
