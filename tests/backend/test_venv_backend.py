from pathlib import Path
from uuid import uuid4
import os

import pytest
from git import Repo

from arca import Arca, VenvBackend, Task


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
    ["requirements_location", "file_location"],
    [
        (None, None),
        ("requirements/requirements.txt", None),
        (None, "test_package"),
        ("requirements/requirements.txt", "test_package"),
    ]
)
def test_venv_backend(requirements_location, file_location):
    kwargs = {}

    if requirements_location is not None:
        kwargs["requirements_location"] = requirements_location

    if file_location is not None:
        kwargs["cwd"] = file_location

    if os.environ.get("TRAVIS", False):
        base_dir = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
    else:
        base_dir = "/tmp/arca/test"

    backend = VenvBackend(base_dir=base_dir, **kwargs)

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

    if requirements_location is None:
        requirements_path = git_dir / "requirements.txt"
    else:
        requirements_path = git_dir / requirements_location

    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    result = arca.run(f"file://{git_dir}", "master", task)
    assert result.success
    assert result.result == "1.11.4"

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
