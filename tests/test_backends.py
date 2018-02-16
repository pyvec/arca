from pathlib import Path
from uuid import uuid4
import os

import itertools
import pytest
from git import Repo

from arca import Arca, VenvBackend, DockerBackend, Task, CurrentEnvironmentBackend
from arca.exceptions import BuildError

from common import BASE_DIR, RETURN_DJANGO_VERSION_FUNCTION, RETURN_STR_FUNCTION, SECOND_RETURN_STR_FUNCTION, \
    TEST_UNICODE, ARG_STR_FUNCTION, KWARG_STR_FUNCTION


@pytest.mark.parametrize(
    ["backend", "requirements_location", "file_location"], list(itertools.product(
        (VenvBackend, DockerBackend, CurrentEnvironmentBackend),
        (None, "requirements/requirements.txt"),
        (None, "test_package"),
    ))
)
def test_backends(backend, requirements_location, file_location):
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

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    if file_location is None:
        filepath = git_dir / "test_file.py"
    else:
        (git_dir / file_location).mkdir(exist_ok=True, parents=True)
        filepath = git_dir / file_location / "test_file.py"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")
    repo_url = f"file://{git_dir}"

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    result = arca.run(repo_url, "master", task)

    assert result.output == "Some string"

    with filepath.open("w") as fl:
        fl.write(SECOND_RETURN_STR_FUNCTION)

    repo.create_head("new_branch")

    repo.index.add([str(filepath)])
    repo.index.commit("Updated function")

    result = arca.run(repo_url, "master", task)
    assert result.output == TEST_UNICODE

    # in the other branch there's still the original
    result = arca.run(repo_url, "new_branch", task)
    assert result.output == "Some string"

    repo.branches.master.checkout()

    requirements_path = git_dir / backend.requirements_location

    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    result = arca.run(repo_url, "master", task)

    assert result.output == "1.11.4"

    if not isinstance(backend, CurrentEnvironmentBackend):
        with pytest.raises(ModuleNotFoundError):
            import django
            print(django.__version__)
    else:
        import django

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.5")

    repo.index.add([str(requirements_path)])
    repo.index.commit("Updated requirements")

    result = arca.run(repo_url, "master", task)
    assert result.output == "1.11.5"

    django_task = Task(
        "django.get_version",
        imports=["django"]
    )

    result = arca.run(repo_url, "master", django_task)
    assert result.output == "1.11.5"

    django_task_error = Task(
        "django.get_version",
    )

    with pytest.raises(BuildError):
        arca.run(f"file://{git_dir}", "master", django_task_error)

    if isinstance(backend, CurrentEnvironmentBackend):
        backend._uninstall("django")

    filepath.write_text(ARG_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Argument function")

    assert arca.run(repo_url, "master", Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")],
        args=[TEST_UNICODE]
    )).output == TEST_UNICODE[::-1]

    filepath.write_text(KWARG_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Keyword argument function")

    assert arca.run(repo_url, "master", Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")],
        kwargs={"kwarg": TEST_UNICODE}
    )).output == TEST_UNICODE[::-1]
