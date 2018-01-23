from pathlib import Path
from uuid import uuid4

import pytest
from git import Repo

from arca import Arca, CurrentEnvironmentBackend, RequirementsStrategy, Task
from arca.exceptions import ArcaMisconfigured, BuildError, RequirementsMismatch

from common import BASE_DIR, RETURN_STR_FUNCTION, RETURN_DJANGO_VERSION_FUNCTION


def test_current_environment_requirements():
    # current_environment_requirements is required
    with pytest.raises(KeyError):
        Arca(backend=CurrentEnvironmentBackend(verbosity=2), base_dir=BASE_DIR)

    requirements_path = str(uuid4()) + ".txt"

    # no such file exists
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=CurrentEnvironmentBackend(
            verbosity=2,
            current_environment_requirements=requirements_path
        ), base_dir=BASE_DIR)

    requirements_path = Path(BASE_DIR) / requirements_path
    requirements_path.touch()

    # ok when the file exists
    Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=requirements_path
    ), base_dir=BASE_DIR)

    # ok when it's set there's no requirements file
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


@pytest.mark.parametrize("strategy", ["ignore", RequirementsStrategy.IGNORE])
def test_strategy_ignore(mocker, strategy):
    install_requirements = mocker.patch.object(CurrentEnvironmentBackend, "install_requirements")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())
    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"
    repo_url = f"file://{git_dir}"
    branch = "master"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(repo_url, branch, task).output == "Some string"
    assert install_requirements.call_count == 0

    repo.create_head("no_requirements")  # keep a reference to when the repo had no requirements, needed later
    repo.branches.master.checkout()

    requirements_path = git_dir / arca.backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")
    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    # now the repository has got requirements
    # install still not called but the task should fail because django is not installed
    with pytest.raises(BuildError):
        arca.run(repo_url, branch, task)
    assert install_requirements.call_count == 0

    current_env_requirements = Path(BASE_DIR) / (str(uuid4()) + ".txt")
    with current_env_requirements.open("w") as fl:
        fl.write("django==1.11.4")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=str(current_env_requirements.resolve()),
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    # now both the current env and the repo have requirements
    # install still not called but the task should fail because django is not installed
    with pytest.raises(BuildError):
        arca.run(repo_url, branch, task)
    assert install_requirements.call_count == 0

    # even when the requirements are not the same
    with current_env_requirements.open("w") as fl:
        fl.write("six")
    with pytest.raises(BuildError):
        arca.run(repo_url, branch, task)
    assert install_requirements.call_count == 0

    # and now we test everything still works when the req. file is missing from repo
    assert arca.run(repo_url, "no_requirements", task).output == "Some string"
    assert install_requirements.call_count == 0


@pytest.mark.parametrize("strategy", ["raise", RequirementsStrategy.RAISE])
def test_strategy_raise(strategy):
    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())
    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"
    repo_url = f"file://{git_dir}"
    branch = "master"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(repo_url, branch, task).output == "Some string"

    repo.create_head("no_requirements")  # keep a reference to when the repo had no requirements, needed later
    repo.branches.master.checkout()

    requirements_path = git_dir / arca.backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")
    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    # Run should raise a exception because there's now extra requirements in the repo
    with pytest.raises(RequirementsMismatch):
        arca.run(repo_url, branch, task)

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
        arca.run(repo_url, branch, task)

    # an extra requirement when current env. reqs. are set
    with current_env_requirements.open("w") as fl:
        fl.write("six")
    with pytest.raises(RequirementsMismatch):
        arca.run(repo_url, branch, task)

    # and now we test everything still works when the req. file is missing from repo but env. reqs. are set
    assert arca.run(repo_url, "no_requirements", task).output == "Some string"


@pytest.mark.parametrize("strategy", ["install_extra", RequirementsStrategy.INSTALL_EXTRA])
def test_strategy_install_extra(mocker, strategy):
    install_requirements = mocker.spy(CurrentEnvironmentBackend, "install_requirements")

    arca = Arca(backend=CurrentEnvironmentBackend(
        verbosity=2,
        current_environment_requirements=None,
        requirements_strategy=strategy
    ), base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())
    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"
    repo_url = f"file://{git_dir}"
    branch = "master"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    # nor the current env or the repo has any requirements, install requirements is not called at all
    assert arca.run(repo_url, branch, task).output == "Some string"
    assert install_requirements.call_count == 0

    repo.create_head("no_requirements")  # keep a reference to when the repo had no requirements, needed later
    repo.branches.master.checkout()

    requirements_path = git_dir / arca.backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")
    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    # Repository now contains a requirement while the current env has none - install is called with whole file
    assert arca.run(repo_url, branch, task).output == "1.11.4"
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
    assert arca.run(repo_url, branch, task).output == "1.11.4"
    assert install_requirements.call_count == 1

    with current_env_requirements.open("w") as fl:
        fl.write("six")

    # requirements are now not the same, install is called again
    assert arca.run(repo_url, branch, task).output == "1.11.4"
    assert install_requirements.call_count == 2

    # and now we test everything still works when the req. file is missing from repo but env. reqs. are set
    assert arca.run(repo_url, "no_requirements", task).output == "Some string"

    arca.backend._uninstall("django")
