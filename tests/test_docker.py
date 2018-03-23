import hashlib
from datetime import datetime

import pytest

from arca import Arca, DockerBackend, Task
from arca.exceptions import ArcaMisconfigured
from common import (RETURN_COLORAMA_VERSION_FUNCTION, BASE_DIR, RETURN_PLATFORM,
                    RETURN_IS_LXML_INSTALLED, RETURN_PYTHON_VERSION_FUNCTION, RETURN_IS_XSLTPROC_INSTALLED)


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
    # TODO: maybe find something that installs quicker than lxml. Becase lxml takes a long time to compile.
    backend = DockerBackend(verbosity=2, apk_dependencies=["libxml2-dev", "libxslt-dev"])

    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.fl.write_text(RETURN_IS_XSLTPROC_INSTALLED)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_is_xsltproc_installed")
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == 0

    requirements_path = temp_repo_func.path / "requirements.txt"
    requirements_path.write_text("lxml")

    temp_repo_func.fl.write_text(RETURN_IS_LXML_INSTALLED)
    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements, changed to lxml")

    task = Task("test_file:return_is_lxml_installed")
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

    temp_repo_func.fl.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.7")  # Has to be unique!

    temp_repo_func.repo.index.add([str(temp_repo_func.fl), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function",)

    mocker.spy(backend, "create_image")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.7"
    assert backend.create_image.call_count == 1

    image = backend.get_or_create_environment(temp_repo_func.url, temp_repo_func.branch,
                                              temp_repo_func.repo, temp_repo_func.path)
    backend.client.images.remove(image.id, force=True)

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.7"
    assert backend.create_image.call_count == 1


def test_inherit_image_with_dependecies():
    backend = DockerBackend(inherit_image="python:alpine3.6", apk_dependencies=["libxml2-dev", "libxslt-dev"])
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)
