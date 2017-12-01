from pathlib import Path
from uuid import uuid4
import os

import pytest
from git import Repo

from arca import Arca, DockerBackend, Task


RETURN_STR_FUNCTION = """
def return_str_function():
    return "Some string"
"""

RETURN_PYTHON_VERSION_FUNCTION = """
import sys

def return_python_version():
    return "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
"""


def test_keep_container_running():
    kwargs = {}

    if os.environ.get("TRAVIS", False):
        base_dir = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
    else:
        base_dir = "/tmp/arca/test"

    backend = DockerBackend(base_dir=base_dir, verbosity=2, keep_container_running=True, **kwargs)

    arca = Arca(backend=backend)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    backend.check_docker_access()   # init docker client

    container_count = len(backend.client.containers.list())

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    count_after_run = len(backend.client.containers.list())

    assert count_after_run == container_count + 1  # let's assume no changes are done to containers elsewhere

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    count_after_second_run = len(backend.client.containers.list())

    assert count_after_second_run == container_count + 1  # the count is still the same

    backend.stop_containers()

    count_after_stop = len(backend.client.containers.list())

    assert count_after_stop == container_count


@pytest.mark.parametrize("python_version", ["3.6.0", "3.6.3"])
def test_python_version(python_version):
    kwargs = {}

    if os.environ.get("TRAVIS", False):
        base_dir = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
    else:
        base_dir = "/tmp/arca/test"

    backend = DockerBackend(base_dir=base_dir, verbosity=2,
                            python_version=python_version, **kwargs)

    arca = Arca(backend=backend)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

    filepath.write_text(RETURN_PYTHON_VERSION_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_python_version",
        from_imports=[("test_file", "return_python_version")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    try:
        print(result.error)
    except AttributeError:
        pass

    assert result.success
    assert result.result == python_version
