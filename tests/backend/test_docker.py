import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from datetime import datetime
from git import Repo

from arca import Arca, DockerBackend, Task
from test_backends import RETURN_DJANGO_VERSION_FUNCTION, RETURN_STR_FUNCTION, BASE_DIR


RETURN_PYTHON_VERSION_FUNCTION = """
import sys

def return_python_version():
    return "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
"""

RETURN_IS_XSLTPROC_INSTALLED = """
import subprocess

def return_is_xsltproc_installed():
    try:
        return subprocess.Popen(["xsltpoc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).wait()
    except:
        return False
"""


RETURN_IS_LXML_INSTALLED = """
def return_is_lxml_installed():
    try:
        import lxml
        return True
    except:
        return False
"""


RETURN_PLATFORM = """
import platform

def return_platform():
    return platform.dist()[0]
"""


def test_keep_container_running():
    backend = DockerBackend(verbosity=2, keep_container_running=True)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

    filepath.write_text(RETURN_STR_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    backend.check_docker_access()   # init docker client

    container_count = len(backend.client.containers.list())

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    count_after_run = len(backend.client.containers.list())

    assert count_after_run == container_count + 1  # let's assume no changes are done to containers elsewhere

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success
    assert result.result == "Some string"

    count_after_second_run = len(backend.client.containers.list())

    assert count_after_second_run == container_count + 1  # the count is still the same

    backend.stop_containers()

    count_after_stop = len(backend.client.containers.list())

    assert count_after_stop == container_count


@pytest.mark.parametrize("python_version", ["3.6.0", "3.6.3"])
def test_python_version(python_version):
    backend = DockerBackend(verbosity=2, python_version=python_version)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

    filepath.write_text(RETURN_PYTHON_VERSION_FUNCTION)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_python_version",
        from_imports=[("test_file", "return_python_version")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    try:
        print(result.error)
    except AttributeError:
        pass

    assert result.success
    assert result.result == python_version


def test_apk_dependencies():
    # TODO: maybe find something that installs quicker than lxml. Becase lxml takes a long time to compile.
    backend = DockerBackend(verbosity=2, apk_dependencies=["libxml2-dev", "libxslt-dev"])

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

    filepath.write_text(RETURN_IS_XSLTPROC_INSTALLED)
    repo.index.add([str(filepath)])
    repo.index.commit("Initial")

    task = Task(
        "return_is_xsltproc_installed",
        from_imports=[("test_file", "return_is_xsltproc_installed")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    try:
        print(result.error)
    except AttributeError:
        pass

    assert result.success
    assert result.result == 0

    requirements_path = git_dir / "requirements.txt"

    with filepath.open("w") as fl:
        fl.write(RETURN_IS_LXML_INSTALLED)

    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("lxml")

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to lxml")

    task = Task(
        "return_is_lxml_installed",
        from_imports=[("test_file", "return_is_lxml_installed")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    try:
        print(result.error)
    except AttributeError:
        pass

    assert result.success
    assert result.result


def test_inherit_image():
    backend = DockerBackend(verbosity=2, inherit_image="python:3.6")

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    filepath = git_dir / "test_file.py"

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

    filepath.write_text(RETURN_PLATFORM)
    repo.index.add([str(filepath)])
    repo.index.commit("Platform")

    task = Task(
        "return_platform",
        from_imports=[("test_file", "return_platform")]
    )

    result = arca.run(f"file://{git_dir}", "master", task)

    assert result.success

    # alpine is the default, dist() returns ('', '', '') on - so this fails when the default image is used
    assert result.result == "debian"

    requirements_path = git_dir / backend.requirements_location

    with filepath.open("w") as fl:
        fl.write(RETURN_DJANGO_VERSION_FUNCTION)

    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.4")

    repo.index.add([str(filepath)])
    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements, changed to version")

    django_task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    result = arca.run(f"file://{git_dir}", "master", django_task)
    try:
        print(result.error)
    except AttributeError:
        pass
    assert result.success
    assert result.result == "1.11.4"


def test_push_to_registry(mocker):
    class LocalDockerBackend(DockerBackend):
        """ A subclass that adds random 10 characters to the tag name so we can start the test with empty slate
            everytime. (When `push_to_repository_name` is used, a pull is launched. Since the requirements are always
            the same, the image would always be pulled and never pushed.)
        """
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.tag_prefix = hashlib.sha1(str(datetime.now()).encode("utf-8")).hexdigest()[:10]

        def get_image_tag(self, requirements_file, dependencies):
            tag = super().get_image_tag(requirements_file, dependencies)

            return f"{self.tag_prefix}_{tag}"

    backend = LocalDockerBackend(verbosity=2, push_to_registry_name="docker.io/mikicz/arca-test")
    arca = Arca(backend=backend, base_dir=BASE_DIR)
    git_dir = Path("/tmp/arca/") / str(uuid4())
    git_repo = Repo.init(git_dir)

    filepath = git_dir / "test_file.py"
    filepath.write_text(RETURN_DJANGO_VERSION_FUNCTION)
    git_repo.index.add([str(filepath)])

    requirements_path = git_dir / backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)
    with requirements_path.open("w") as fl:
        fl.write("django==1.11.3")  # Has to be unique!
    git_repo.index.add([str(requirements_path)])

    git_repo.index.commit("Initial")

    task = Task(
        "return_str_function",
        from_imports=[("test_file", "return_str_function")]
    )

    repo = f"file://{git_dir}"
    branch = "master"

    mocker.spy(backend, "create_image")

    result = arca.run(repo, branch, task)

    assert result.success
    assert result.result == "1.11.3"
    assert backend.create_image.call_count == 1

    image = backend.get_or_create_environment(repo, branch, git_repo, git_dir)
    backend.client.images.remove(image.id, force=True)

    result = arca.run(repo, branch, task)

    assert result.success
    assert result.result == "1.11.3"

    assert backend.create_image.call_count == 1


def test_inherit_image_with_dependecies():
    backend = DockerBackend(inherit_image="python:alpine3.6", apk_dependencies=["libxml2-dev", "libxslt-dev"])
    with pytest.raises(ValueError):
        Arca(backend=backend)
