from pathlib import Path
from uuid import uuid4
import os

from git import Repo

from arca import Arca, DockerBackend, Task


RETURN_STR_FUNCTION = """
def return_str_function():
    return "Some string"
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
