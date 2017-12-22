from pathlib import Path
from uuid import uuid4
import os

import itertools
import pytest
from git import Repo

from arca import Arca, VenvBackend, DockerBackend, Task

RETURN_STR_FUNCTION = """
def return_str_function():
    return "Some string"
"""

SECOND_RETURN_STR_FUNCTION = """
def return_str_function():
    return "Some other string"
"""

RETURN_DJANGO_VERSION_FUNCTION = """
import django

def return_str_function():
    return django.__version__
"""


@pytest.mark.parametrize(
    ["backend", "requirements_location", "file_location"], list(itertools.product(
        (VenvBackend, DockerBackend),
        (None, "requirements/requirements.txt"),
        (None, "test_package"),
    ))
)
def test_venv_backend(backend, requirements_location, file_location):
    if os.environ.get("TRAVIS", False) and backend == VenvBackend:
        raise pytest.skip("Venv Backend doesn't work on Travis")

    kwargs = {}

    if requirements_location is not None:
        kwargs["requirements_location"] = requirements_location

    if file_location is not None:
        kwargs["cwd"] = file_location

    if os.environ.get("TRAVIS", False):
        base_dir = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
    else:
        base_dir = "/tmp/arca/test"

    backend = backend(base_dir=base_dir, verbosity=2, **kwargs)

    arca = Arca(backend=backend)

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

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    with filepath.open("w") as fl:
        fl.write(SECOND_RETURN_STR_FUNCTION)

    repo.create_head("new_branch")

    repo.index.add([str(filepath)])
    repo.index.commit("Updated function")

    result = arca.run(f"file://{git_dir}", "master", task)
    assert result.success
    assert result.result == "Some other string"

    # in the other branch there's still the original
    result = arca.run(f"file://{git_dir}", "new_branch", task)
    assert result.success
    assert result.result == "Some string"

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

    result = arca.run(f"file://{git_dir}", "master", task)
    try:
        print(result.error)
    except AttributeError:
        pass
    assert result.success
    assert result.result == "1.11.4"

    with pytest.raises(ModuleNotFoundError):
        import django
        print(django.__version__)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.5")

    repo.index.add([str(requirements_path)])
    repo.index.commit("Updated requirements")

    result = arca.run(f"file://{git_dir}", "master", task)
    assert result.success
    assert result.result == "1.11.5"

    django_task = Task(
        "django.get_version",
        imports=["django"]
    )

    result = arca.run(f"file://{git_dir}", "master", django_task)
    assert result.success
    assert result.result == "1.11.5"

    django_task_error = Task(
        "django.get_version",
    )

    result = arca.run(f"file://{git_dir}", "master", django_task_error)
    assert not result.success


@pytest.mark.parametrize(
    "backend,file_location", list(itertools.product(
        (VenvBackend, DockerBackend),
        ("", "test_location"),
    ))
)
def test_venv_backend_static(backend, file_location):
    if os.environ.get("TRAVIS", False):
        base_dir = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
    else:
        base_dir = "/tmp/arca/test"

    backend = backend(base_dir=base_dir, verbosity=2)

    arca = Arca(backend=backend)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    if not file_location:
        filepath = git_dir / "test_file.txt"
    else:
        (git_dir / file_location).mkdir(exist_ok=True, parents=True)
        filepath = git_dir / file_location / "test_file.txt"

    filepath.write_text("Some test file")
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    relative_path = Path(file_location) / "test_file.txt"

    result = arca.static_filename(f"file://{git_dir}", "master", relative_path)

    assert filepath.read_text() == result.read_text()

    result = arca.static_filename(f"file://{git_dir}", "master", str(relative_path))

    assert filepath.read_text() == result.read_text()
