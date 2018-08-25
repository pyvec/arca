import platform
from pathlib import Path

import pytest

from arca import Arca, DockerBackend, Task
from arca.exceptions import ArcaMisconfigured, PushToRegistryError, BuildError
from common import (RETURN_COLORAMA_VERSION_FUNCTION, BASE_DIR, RETURN_PLATFORM,
                    RETURN_PYTHON_VERSION_FUNCTION, RETURN_ALSAAUDIO_INSTALLED)


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


@pytest.mark.parametrize("python_version", ["3.6.0", platform.python_version()])
def test_python_version(temp_repo_func, python_version):
    backend = DockerBackend(verbosity=2, python_version=python_version)

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.file_path.write_text(RETURN_PYTHON_VERSION_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_python_version")
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == python_version


def test_apt_dependencies(temp_repo_func):
    backend = DockerBackend(verbosity=2, apt_dependencies=["libasound2-dev"])

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    requirements_path = temp_repo_func.repo_path / "requirements.txt"
    requirements_path.write_text("pyalsaaudio==0.8.4")

    temp_repo_func.file_path.write_text(RETURN_ALSAAUDIO_INSTALLED)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to lxml")

    # pyalsaaudio can't be installed if libasound2-dev is missing
    task = Task("test_file:return_alsaaudio_installed")
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output


def test_inherit_image(temp_repo_func):
    backend = DockerBackend(verbosity=2, inherit_image="mikicz/alpine-python-pipenv:latest")

    arca = Arca(backend=backend, base_dir=BASE_DIR)
    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"

    temp_repo_func.file_path.write_text(RETURN_PLATFORM)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Platform")

    task = Task("test_file:return_platform")

    # debian is the default, alpine dist() returns ('', '', '') on - so this fails when the default image is used
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output != "debian"

    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.8")

    temp_repo_func.file_path.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to version")

    colorama_task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task).output == "0.3.8"

    # Pipfile

    pipfile_path = requirements_path.parent / "Pipfile"
    pipfile_lock_path = pipfile_path.parent / "Pipfile.lock"

    pipfile_path.write_text((Path(__file__).parent / "fixtures/Pipfile").read_text("utf-8"))

    temp_repo_func.repo.index.remove([str(requirements_path)])
    temp_repo_func.repo.index.add([str(pipfile_path)])
    temp_repo_func.repo.index.commit("Added Pipfile")

    with pytest.raises(BuildError):  # Only Pipfile
        arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task)

    pipfile_lock_path.write_text((Path(__file__).parent / "fixtures/Pipfile.lock").read_text("utf-8"))

    temp_repo_func.repo.index.remove([str(pipfile_path)])
    temp_repo_func.repo.index.add([str(pipfile_lock_path)])
    temp_repo_func.repo.index.commit("Removed Pipfile, added Pipfile.lock")

    with pytest.raises(BuildError):  # Only Pipfile.lock
        arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task)

    pipfile_path.write_text((Path(__file__).parent / "fixtures/Pipfile").read_text("utf-8"))

    temp_repo_func.repo.index.add([str(pipfile_path)])
    temp_repo_func.repo.index.commit("Added back Pipfile")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task).output == "0.3.9"

    # works even when requirements is in the repo
    requirements_path.write_text("colorama==0.3.8")
    temp_repo_func.repo.index.add([str(requirements_path)])
    temp_repo_func.repo.index.commit("Added back requirements")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, colorama_task).output == "0.3.9"


def test_push_to_registry(temp_repo_func, mocker):
    backend = DockerBackend(verbosity=2, use_registry_name="docker.io/mikicz/arca-test")
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.file_path.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    # even though the image might already exist on the registry, lets pretend it doesn't
    mocker.patch.object(backend, "try_pull_image_from_registry", lambda *args: None)
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    mocker.stopall()

    image = backend.get_image_for_repo(temp_repo_func.url, temp_repo_func.branch,
                                       temp_repo_func.repo, temp_repo_func.repo_path)

    backend.client.images.remove(image.id, force=True)

    mocker.spy(backend, "build_image")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    assert backend.build_image.call_count == 0

    # test push disabled
    mocker.patch.object(backend, "try_pull_image_from_registry", lambda *args: None)

    # untag the image so Arca thinks the images was just built and that it needs to be pushed
    for image in backend.client.images.list("docker.io/mikicz/arca-test"):
        for tag in image.tags:
            if tag.startswith("docker.io/mikicz/arca-test"):
                backend.client.images.remove(tag)

    backend = DockerBackend(verbosity=2, use_registry_name="docker.io/mikicz/arca-test",
                            registry_pull_only=True)
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    mocker.spy(backend, "push_to_registry")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    assert backend.push_to_registry.call_count == 0


def test_push_to_registry_fail(temp_repo_func):
    # when a unused repository name is used, it's created -> different username has to be used
    backend = DockerBackend(verbosity=2, use_registry_name="docker.io/mikicz-unknown-user/arca-test")
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.file_path.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    with pytest.raises(PushToRegistryError):
        assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"


def test_inherit_image_with_dependecies():
    backend = DockerBackend(inherit_image="python:alpine3.6", apt_dependencies=["libasound2-dev"])
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)
