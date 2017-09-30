from pathlib import Path
from uuid import uuid4

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


def test_venv_backend():
    arca = Arca(VenvBackend(base_dir="/tmp/arca/test"))

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    package_path = Path(git_dir) / "test_package.py"

    package_path.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(package_path)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_package", "return_str_function")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    with package_path.open("w") as fl:
        fl.write(SECOND_RETURN_STR_FUNCTION)

    repo.create_head("new_branch")

    repo.index.add([str(package_path)])
    repo.index.commit("Updated function")

    result = arca.run(f"file://{git_dir}", "master", task)
    assert result.success
    assert result.result == "Some other string"

    # in the other branch there's still the original
    result = arca.run(f"file://{git_dir}", "new_branch", task)
    assert result.success
    assert result.result == "Some string"
