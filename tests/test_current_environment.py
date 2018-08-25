import itertools
import subprocess
import sys

import pytest

from arca import Arca, Task, CurrentEnvironmentBackend
from arca.utils import logger
from arca.exceptions import BuildError
from common import BASE_DIR, RETURN_COLORAMA_VERSION_FUNCTION, SECOND_RETURN_STR_FUNCTION, TEST_UNICODE


def _pip_action(action, package):
    if action not in ["install", "uninstall"]:
        raise ValueError(f"{action} is invalid value for action")

    cmd = [sys.executable, "-m", "pip", action]

    if action == "uninstall":
        cmd += ["-y"]

    cmd += [package]

    logger.info("Installing requirements with command: %s", cmd)

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out_stream, err_stream = process.communicate()

    out_stream = out_stream.decode("utf-8")
    err_stream = err_stream.decode("utf-8")

    logger.debug("Return code is %s", process.returncode)
    logger.debug(out_stream)
    logger.debug(err_stream)


@pytest.mark.parametrize(
    ["requirements_location", "file_location"], list(itertools.product(
        (None, "requirements/requirements.txt"),
        (None, "test_package"),
    ))
)
def test_current_environment_backend(temp_repo_func, requirements_location, file_location):
    """ Tests the basic stuff around backends, if it can install requirements from more locations,
        launch stuff with correct cwd, works well with multiple branches, etc
    """
    kwargs = {}

    if requirements_location is not None:
        kwargs["requirements_location"] = requirements_location

    if file_location is not None:
        kwargs["cwd"] = file_location

    backend = CurrentEnvironmentBackend(verbosity=2, **kwargs)

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

    temp_repo_func.repo.branches.master.checkout()

    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)
    requirements_path.write_text("colorama==0.3.9")

    filepath.write_text(RETURN_COLORAMA_VERSION_FUNCTION)

    temp_repo_func.repo.index.add([str(filepath), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    # check that it's not installed from previous tests
    _pip_action("uninstall", "colorama")

    with pytest.raises(ModuleNotFoundError):
        import colorama  # noqa

    # CurrentEnv fails because it ignores requirements
    with pytest.raises(BuildError):
        assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    # but when it's installed locally then it succeeds
    _pip_action("install", "colorama==0.3.9")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    # cleanup

    _pip_action("uninstall", "colorama")

    with pytest.raises(ModuleNotFoundError):
        import colorama  # noqa
