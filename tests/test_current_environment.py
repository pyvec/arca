from pathlib import Path
from uuid import uuid4

import pytest

from arca import Arca, CurrentEnvironmentBackend, RequirementsStrategy, Task
from arca.exceptions import ArcaMisconfigured, BuildError, RequirementsMismatch
from common import BASE_DIR, RETURN_DJANGO_VERSION_FUNCTION


def test_current_environment_requirements():
    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None
    ), base_dir=BASE_DIR)

    # test how installing nonexisting packages is handled
    with pytest.raises(BuildError):
        arca.backend.install_requirements(requirements=[str(uuid4())])

    with pytest.raises(ValueError):
        arca.backend.install_requirements()

    with pytest.raises(ValueError):
        arca.backend.install_requirements(requirements=["django"], _action="remove")


def test_requirements_strategy():
    """ Test validation of invalid strategies
    """

    with pytest.raises(ValueError):
        Arca(backend=CurrentEnvironmentBackend(
            verbosity=2,
            current_environment_requirements=None,
            requirements_strategy="nonexistant_strategy"
        ), base_dir=BASE_DIR)

    with pytest.raises(ValueError):
        arca = Arca(base_dir=BASE_DIR, settings={
            "ARCA_BACKEND": "arca.backend.CurrentEnvironmentBackend",
            "ARCA_BACKEND_VERBOSITY": 2,
            "ARCA_BACKEND_CURRENT_ENVIRONMENT_REQUIREMENTS": None,
            "ARCA_BACKEND_REQUIREMENTS_STRATEGY": "nonexistant_strategy"
        })
        print(arca.backend.requirements_strategy)


@pytest.mark.parametrize("strategy", ["ignore", RequirementsStrategy.IGNORE])
def test_strategy_ignore(mocker, temp_repo_func, strategy):
    install_requirements = mocker.patch.object(CurrentEnvironmentBackend, "install_requirements")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    task = Task("test_file:return_str_function")

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert install_requirements.call_count == 0

    # keep a reference to when the repo had no requirements, needed later
    temp_repo_func.repo.create_head("no_requirements")
    temp_repo_func.repo.branches.master.checkout()

    requirements_path = temp_repo_func.path / arca.backend.requirements_location
    requirements_path.write_text("django==1.11.4")

    temp_repo_func.fl.write_text(RETURN_DJANGO_VERSION_FUNCTION)

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    # now the repository has got requirements
    # install still not called but the task should fail because django is not installed
    with pytest.raises(BuildError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)
    assert install_requirements.call_count == 0

    current_env_requirements = Path(BASE_DIR) / (str(uuid4()) + ".txt")
    current_env_requirements_non_existent = Path(BASE_DIR) / (str(uuid4()) + ".txt")

    with current_env_requirements.open("w") as fl:
        fl.write("django==1.11.4")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str(current_env_requirements.resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    arca_nonexistent_req = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str(current_env_requirements_non_existent.resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    # now both the current env and the repo have requirements
    # install still not called but the task should fail because django is not installed
    with pytest.raises(BuildError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    # same result even when the current env requirements don't exist
    with pytest.raises(BuildError):
        arca_nonexistent_req.run(temp_repo_func.url, temp_repo_func.branch, task)

    assert install_requirements.call_count == 0

    # even when the requirements are not the same
    with current_env_requirements.open("w") as fl:
        fl.write("six")
    with pytest.raises(BuildError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    assert install_requirements.call_count == 0

    # and now we test everything still works when the req. file is missing from repo
    assert arca.run(temp_repo_func.url, "no_requirements", task).output == "Some string"
    assert arca_nonexistent_req.run(temp_repo_func.url, "no_requirements", task).output == "Some string"

    assert install_requirements.call_count == 0


@pytest.mark.parametrize("strategy", ["raise", RequirementsStrategy.RAISE])
def test_strategy_raise(temp_repo_func, strategy):
    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)
    arca_non_existent = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str((Path(BASE_DIR) / (str(uuid4()) + ".txt")).resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    task = Task("test_file:return_str_function")

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    # even when the current env. req. file doesn't exist
    assert arca_non_existent.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    # keep a reference to when the repo had no requirements, needed later
    temp_repo_func.repo.create_head("no_requirements")
    temp_repo_func.repo.branches.master.checkout()

    requirements_path = temp_repo_func.path / arca.backend.requirements_location
    requirements_path.write_text("django==1.11.4")

    temp_repo_func.fl.write_text(RETURN_DJANGO_VERSION_FUNCTION)

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    # Run should raise a exception because there's now extra requirements in the repo
    with pytest.raises(RequirementsMismatch):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    # raise different exception when can't compare to current env because it's missing
    with pytest.raises(ArcaMisconfigured):
        arca_non_existent.run(temp_repo_func.url, temp_repo_func.branch, task)

    current_env_requirements = Path(BASE_DIR) / (str(uuid4()) + ".txt")
    with current_env_requirements.open("w") as fl:
        fl.write("django==1.11.4")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str(current_env_requirements.resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    # now both the current env and the repo have the same requirements
    # run should fail not because of mismatch, but because django is not actually installed
    with pytest.raises(BuildError):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    # an extra requirement when current env. reqs. are set
    with current_env_requirements.open("w") as fl:
        fl.write("six")
    with pytest.raises(RequirementsMismatch):
        arca.run(temp_repo_func.url, temp_repo_func.branch, task)

    # and now we test everything still works when the req. file is missing from repo but env. reqs. are set
    assert arca.run(temp_repo_func.url, "no_requirements", task).output == "Some string"


@pytest.mark.parametrize("strategy", ["install_extra", RequirementsStrategy.INSTALL_EXTRA])
def test_strategy_install_extra(temp_repo_func, mocker, strategy):
    install_requirements = mocker.spy(CurrentEnvironmentBackend, "install_requirements")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    arca_non_existent = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str((Path(BASE_DIR) / (str(uuid4()) + ".txt")).resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    task = Task("test_file:return_str_function")

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    # even when the current env file is missing
    assert arca_non_existent.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    assert install_requirements.call_count == 0

    # keep a reference to when the repo had no requirements, needed later
    temp_repo_func.repo.create_head("no_requirements")
    temp_repo_func.repo.branches.master.checkout()

    requirements_path = temp_repo_func.path / arca.backend.requirements_location
    requirements_path.write_text("django==1.11.4")
    temp_repo_func.fl.write_text(RETURN_DJANGO_VERSION_FUNCTION)

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    # Repository now contains a requirement while the current env has none - install is called with whole file
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "1.11.4"

    # but raises exception when can't compare because the current env file is missing
    with pytest.raises(ArcaMisconfigured):
        arca_non_existent.run(temp_repo_func.url, temp_repo_func.branch, task)

    assert install_requirements.call_count == 1

    current_env_requirements = Path(BASE_DIR) / (str(uuid4()) + ".txt")
    with current_env_requirements.open("w") as fl:
        fl.write("django==1.11.4")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str(current_env_requirements.resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    # now both the current env and the repo have the same requirements, call count shouldn't increase
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "1.11.4"
    assert install_requirements.call_count == 1

    with current_env_requirements.open("w") as fl:
        fl.write("six")

    # requirements are now not the same, install is called again
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "1.11.4"
    assert install_requirements.call_count == 2

    # and now we test everything still works when the req. file is missing from repo but env. reqs. are set
    assert arca.run(temp_repo_func.url, "no_requirements", task).output == "Some string"

    arca.backend._uninstall("django")
