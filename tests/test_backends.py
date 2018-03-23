import itertools
import os

import pytest

from arca import Arca, VenvBackend, DockerBackend, Task, CurrentEnvironmentBackend
from common import BASE_DIR, RETURN_COLORAMA_VERSION_FUNCTION, SECOND_RETURN_STR_FUNCTION, \
    TEST_UNICODE, ARG_STR_FUNCTION, KWARG_STR_FUNCTION


@pytest.mark.parametrize(
    ["backend", "requirements_location", "file_location"], list(itertools.product(
        (VenvBackend, DockerBackend, CurrentEnvironmentBackend),
        (None, "requirements/requirements.txt"),
        (None, "test_package"),
    ))
)
def test_backends(temp_repo_func, backend, requirements_location, file_location):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}

    if requirements_location is not None:
        kwargs["requirements_location"] = requirements_location

    if file_location is not None:
        kwargs["cwd"] = file_location

    if backend == DockerBackend:
        kwargs["disable_pull"] = True
    if backend == CurrentEnvironmentBackend:
        kwargs["current_environment_requirements"] = None
        kwargs["requirements_strategy"] = "install_extra"

    backend = backend(verbosity=2, **kwargs)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    if file_location is None:
        filepath = temp_repo_func.fl
    else:
        filepath = temp_repo_func.path / file_location / "test_file.py"
        filepath.parent.mkdir(exist_ok=True, parents=True)
        temp_repo_func.fl.replace(filepath)

        temp_repo_func.repo.index.remove([str(temp_repo_func.fl)])
        temp_repo_func.repo.index.add([str(filepath)])
        temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function",)

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    filepath.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.create_head("new_branch")
    temp_repo_func.repo.index.add([str(filepath)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE

    # in the other branch there's still the original
    assert arca.run(temp_repo_func.url, "new_branch", task).output == "Some string"

    temp_repo_func.repo.branches.master.checkout()

    requirements_path = temp_repo_func.path / backend.requirements_location
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

    if isinstance(backend, CurrentEnvironmentBackend):
        backend._uninstall("colorama")

    with pytest.raises(ModuleNotFoundError):
        import colorama  # noqa
