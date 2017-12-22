from pathlib import Path
from uuid import uuid4

import os
import pytest
from git import Repo

from arca import Arca, DockerBackend, Task, VenvBackend
from test_backends import RETURN_STR_FUNCTION, SECOND_RETURN_STR_FUNCTION, BASE_DIR


@pytest.mark.parametrize(
    "backend", [VenvBackend, DockerBackend],
)
def test_single_pull(mocker, backend):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}
    if backend == DockerBackend:
        kwargs["disable_pull"] = True

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR, single_pull=True)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"
    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    mocker.spy(arca, "_pull")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )
    repo_url = f"file://{git_dir}"

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some string"
    assert arca._pull.call_count == 1

    with filepath.open("w") as fl:
        fl.write(SECOND_RETURN_STR_FUNCTION)

    repo.index.add([str(filepath)])
    repo.index.commit("Updated function")

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some string"
    assert arca._pull.call_count == 1

    arca.pull_again(repo_url, "master")

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some other string"
    assert arca._pull.call_count == 2


@pytest.mark.parametrize(
    "backend", [VenvBackend, DockerBackend],
)
def test_pull_efficiency(mocker, backend):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}
    if backend == DockerBackend:
        kwargs["disable_pull"] = True

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"
    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    mocker.spy(arca, "_pull")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )
    repo_url = f"file://{git_dir}"

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some string"
    assert arca._pull.call_count == 1

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some string"
    assert arca._pull.call_count == 2

    with filepath.open("w") as fl:
        fl.write(SECOND_RETURN_STR_FUNCTION)

    repo.index.add([str(filepath)])
    repo.index.commit("Updated function")

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some other string"
    assert arca._pull.call_count == 3

    result = arca.run(repo_url, "master", task)
    assert result.success
    assert result.result == "Some other string"
    assert arca._pull.call_count == 4
