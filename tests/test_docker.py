import pytest

from arca import Arca, DockerBackend, Task
from arca.exceptions import ArcaMisconfigured, PushToRegistryError
from common import (RETURN_COLORAMA_VERSION_FUNCTION, BASE_DIR, RETURN_PLATFORM,
                    RETURN_PYTHON_VERSION_FUNCTION, RETURN_FREETYPE_VERSION)


def test_keep_container_running(temp_repo_func):
    backend = DockerBackend(verbosity=2, keep_container_running=True)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    task = Task("test_file:return_str_function")

    backend.check_docker_access()   # init docker client

    container_count = len(backend.client.containers.list())

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    count_after_run = len(backend.client.containers.list())

    assert count_after_run == container_count + 1  # let's assume no changes are done to containers elsewhere
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    count_after_second_run = len(backend.client.containers.list())

    assert count_after_second_run == container_count + 1  # the count is still the same

    backend.stop_containers()

    count_after_stop = len(backend.client.containers.list())

    assert count_after_stop == container_count


@pytest.mark.parametrize("python_version", ["3.6.0", "3.6.3"])
def test_python_version(temp_repo_func, python_version):
    backend = DockerBackend(verbosity=2, python_version=python_version)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.fl.write_text(RETURN_PYTHON_VERSION_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_python_version")
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == python_version


def test_apk_dependencies(temp_repo_func):
    backend = DockerBackend(verbosity=2, apk_dependencies=["freetype-dev"])

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    requirements_path = temp_repo_func.path / "requirements.txt"
    requirements_path.write_text("freetype-py")

    temp_repo_func.fl.write_text(RETURN_FREETYPE_VERSION)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to lxml")

    # ``import freetype`` raises an error if the library ``freetype-dev`` is not installed
    task = Task("test_file:return_freetype_version")
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output


def test_inherit_image(temp_repo_func):
    backend = DockerBackend(verbosity=2, inherit_image="python:3.6")

    arca = Arca(backend=backend, base_dir=BASE_DIR)
    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    temp_repo_func.fl.write_text(RETURN_PLATFORM)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl)])
    temp_repo_func.repo.index.commit("Platform")

    task = Task("test_file:return_platform")

    # alpine is the default, dist() returns ('', '', '') on - so this fails when the default image is used
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "debian"

    requirements_path = temp_repo_func.path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.fl.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    colorama_task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task).output == "0.3.9"


def test_push_to_registry(temp_repo_func, mocker):
    backend = DockerBackend(verbosity=2, push_to_registry_name="docker.io/mikicz/arca-test")
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.fl.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    # even though the image might already exist on the registry, lets pretend it doesn't
    mocker.patch.object(backend, "try_pull_image_from_registry", lambda *args: None)
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    mocker.stopall()

    image = backend.get_or_create_environment(temp_repo_func.url, temp_repo_func.branch,
                                              temp_repo_func.repo, temp_repo_func.path)

    backend.client.images.remove(image.id, force=True)

    mocker.spy(backend, "create_image")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    assert backend.create_image.call_count == 0


def test_push_to_registry_fail(temp_repo_func):
    # when a unused repository name is used, it's created -> different username has to be used
    backend = DockerBackend(verbosity=2, push_to_registry_name="docker.io/mikicz-unknown-user/arca-test")
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.fl.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    with pytest.raises(PushToRegistryError):
        assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"


def test_inherit_image_with_dependecies():
    backend = DockerBackend(inherit_image="python:alpine3.6", apk_dependencies=["freetype-dev"])
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)
