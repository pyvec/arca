import itertools
import os
from pathlib import Path

import pytest

from arca import Arca, VenvBackend, DockerBackend, Task, CurrentEnvironmentBackend
from arca.exceptions import BuildTimeoutError, BuildError
from common import BASE_DIR, RETURN_COLORAMA_VERSION_FUNCTION, SECOND_RETURN_STR_FUNCTION, \
    TEST_UNICODE, ARG_STR_FUNCTION, KWARG_STR_FUNCTION, WAITING_FUNCTION, RETURN_STR_FUNCTION


@pytest.mark.parametrize(
    ["backend", "requirements_location", "file_location"], list(itertools.product(
        (VenvBackend, DockerBackend),
        (None, "requirements/requirements.txt"),
        (None, "test_package"),
    ))
)
def test_backends(temp_repo_func, backend, requirements_location, file_location):
    """ Tests the basic stuff around backends, if it can install requirements from more locations,
        launch stuff with correct cwd, works well with multiple branches, etc
    """
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}

    if requirements_location is not None:
        kwargs["requirements_location"] = requirements_location
        kwargs["pipfile_location"] = requirements_location.split("/")[0]

    if file_location is not None:
        kwargs["cwd"] = file_location

    if backend == DockerBackend:
        kwargs["disable_pull"] = True

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    if file_location is None:
        filepath = temp_repo_func.file_path
    else:
        filepath = temp_repo_func.repo_path / file_location / "test_file.py"
        filepath.parent.mkdir(exist_ok=True, parents=True)
        temp_repo_func.file_path.replace(filepath)

        temp_repo_func.repo.index.remove([str(temp_repo_func.file_path)])
        temp_repo_func.repo.index.add([str(filepath)])
        temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    filepath.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.create_head("new_branch")
    temp_repo_func.repo.create_tag("test_tag")
    temp_repo_func.repo.index.add([str(filepath)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE

    # in the other branch there's still the original
    assert arca.run(temp_repo_func.url, "new_branch", task).output == "Some string"
    # test that tags work as well
    assert arca.run(temp_repo_func.url, "test_tag", task).output == "Some string"

    temp_repo_func.repo.branches[temp_repo_func.branch].checkout()

    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)
    requirements_path.write_text("colorama==0.3.9")

    filepath.write_text(RETURN_COLORAMA_VERSION_FUNCTION)

    temp_repo_func.repo.index.add([str(filepath), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    requirements_path.write_text("colorama==0.3.8")

    temp_repo_func.repo.index.add([str(requirements_path)])
    temp_repo_func.repo.index.commit("Updated requirements")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.8"

    # Pipfile

    pipfile_path = requirements_path.parent / "Pipfile"
    pipfile_lock_path = pipfile_path.parent / "Pipfile.lock"

    pipfile_path.write_text((Path(__file__).parent / "fixtures/Pipfile").read_text("utf-8"))

    temp_repo_func.repo.index.remove([str(requirements_path)])
    temp_repo_func.repo.index.add([str(pipfile_path)])
    temp_repo_func.repo.index.commit("Added Pipfile")

    with pytest.raises(BuildError):  # Only Pipfile
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    pipfile_lock_path.write_text((Path(__file__).parent / "fixtures/Pipfile.lock").read_text("utf-8"))

    temp_repo_func.repo.index.remove([str(pipfile_path)])
    temp_repo_func.repo.index.add([str(pipfile_lock_path)])
    temp_repo_func.repo.index.commit("Removed Pipfile, added Pipfile.lock")

    with pytest.raises(BuildError):  # Only Pipfile.lock
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    pipfile_path.write_text((Path(__file__).parent / "fixtures/Pipfile").read_text("utf-8"))

    temp_repo_func.repo.index.add([str(pipfile_path)])
    temp_repo_func.repo.index.commit("Added back Pipfile")

    # works even when requirements is in the repo
    requirements_path.write_text("colorama==0.3.8")
    temp_repo_func.repo.index.add([str(requirements_path)])
    temp_repo_func.repo.index.commit("Added back requirements")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    pipfile_lock_path.write_text((Path(__file__).parent / "fixtures/Pipfile.lock.invalid").read_text("utf-8"))

    temp_repo_func.repo.index.add([str(pipfile_lock_path)])
    temp_repo_func.repo.index.commit("Broke Pipfile.lock")

    with pytest.raises(BuildError):  # Invalid Pipfile.lock
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    # cleanup

    with pytest.raises(ModuleNotFoundError):
        import colorama  # noqa


@pytest.mark.parametrize(
    "backend",
    [CurrentEnvironmentBackend, VenvBackend, DockerBackend]
)
def test_advanced_backends(temp_repo_func, backend):
    """ Tests the more time-intensive stuff, like timeouts or arguments,
        things multiple for runs with different arguments are not neccessary
    """
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}

    if backend == DockerBackend:
        kwargs["disable_pull"] = True
    if backend == CurrentEnvironmentBackend:
        kwargs["current_environment_requirements"] = None
        kwargs["requirements_strategy"] = "install_extra"

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    filepath = temp_repo_func.file_path
    requirements_path = temp_repo_func.repo_path / backend.requirements_location

    filepath.write_text(ARG_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(filepath)])
    temp_repo_func.repo.index.commit("Argument function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, Task(
        "test_file:return_str_function",
        args=[TEST_UNICODE]
    )).output == TEST_UNICODE[::-1]

    filepath.write_text(KWARG_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(filepath)])
    temp_repo_func.repo.index.commit("Keyword argument function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, Task(
        "test_file:return_str_function",
        kwargs={"kwarg": TEST_UNICODE}
    )).output == TEST_UNICODE[::-1]

    # test task timeout
    filepath.write_text(WAITING_FUNCTION)
    temp_repo_func.repo.index.add([str(filepath)])
    temp_repo_func.repo.index.commit("Waiting function")

    task_1_second = Task("test_file:return_str_function", timeout=1)
    task_3_seconds = Task("test_file:return_str_function", timeout=3)

    with pytest.raises(BuildTimeoutError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task_1_second)

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task_3_seconds).output == "Some string"

    # test requirements timeout

    if isinstance(arca.backend, CurrentEnvironmentBackend):
        return  # CurrentEnvironmentBackend ignores requirements

    requirements_path.write_text("scipy")

    filepath.write_text(RETURN_STR_FUNCTION)

    temp_repo_func.repo.index.add([str(filepath), str(requirements_path)])
    temp_repo_func.repo.index.commit("Updated requirements to something that takes > 1 second to install")

    arca.backend.requirements_timeout = 1

    with pytest.raises(BuildTimeoutError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, Task("test_file:return_str_function"))
