import os

import pytest

from arca import Arca, DockerBackend, Task, VenvBackend, CurrentEnvironmentBackend
from common import SECOND_RETURN_STR_FUNCTION, BASE_DIR, TEST_UNICODE


@pytest.mark.parametrize(
    "backend", [VenvBackend, DockerBackend, CurrentEnvironmentBackend],
)
def test_single_pull(temp_repo_func, mocker, backend):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}
    if backend == DockerBackend:
        kwargs["disable_pull"] = True
    if backend == CurrentEnvironmentBackend:
        kwargs["current_environment_requirements"] = None

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR, single_pull=True)

    mocker.spy(arca, "_pull")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    temp_repo_func.file_path.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    arca.pull_again(temp_repo_func.url, temp_repo_func.branch)

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 2


@pytest.mark.parametrize(
    "backend", [VenvBackend, DockerBackend, CurrentEnvironmentBackend],
)
def test_pull_efficiency(temp_repo_func, mocker, backend):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}
    if backend == DockerBackend:
        kwargs["disable_pull"] = True
    if backend == CurrentEnvironmentBackend:
        kwargs["current_environment_requirements"] = None

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    mocker.spy(arca, "_pull")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 2

    temp_repo_func.file_path.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 3

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 4
