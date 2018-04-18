import os

import pytest

from arca import VagrantBackend, Arca, Task
from arca.exceptions import ArcaMisconfigured, BuildError
from common import BASE_DIR, RETURN_COLORAMA_VERSION_FUNCTION


def test_validation():
    if os.environ.get("TRAVIS", False):
        pytest.skip("Vagrant doesn't work on Travis")

    backend = VagrantBackend()

    # VagrantBackend requires `push_to_registry`
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # validation passes
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test")
    Arca(backend=backend)

    # push must be enabled
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test", registry_pull_only=True)
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # valid different box
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test", box="hashicorp/precise64")
    assert Arca(backend=backend).backend.box == "hashicorp/precise64"

    # invalid box
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test", box="ubuntu rusty64\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # valid different provider
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test", provider="vmware_fusion")
    assert Arca(backend=backend).backend.provider == "vmware_fusion"

    # invalid provider
    backend = VagrantBackend(use_registry_name="docker.io/mikicz/arca-test", provider="libvirst\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)


# `hashicorp/boot2docker` contains docker 1.7 - doesn't work
# `asdfkljasdf/asdfasdf` doesn't exist
@pytest.mark.parametrize("box", [None, "hashicorp/boot2docker", "asdfkljasdf/asdfasdf"])
def test_vagrant(temp_repo_func, box):
    if os.environ.get("TRAVIS", False):
        pytest.skip("Vagrant doesn't work on Travis")

    kwargs = {}
    if box:
        kwargs["box"] = box
    backend = VagrantBackend(verbosity=2, use_registry_name="docker.io/mikicz/arca-test", **kwargs)
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    temp_repo_func.file_path.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")

    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    task = Task("test_file:return_str_function")

    if not box:
        assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    else:
        with pytest.raises(BuildError):  # fails because of reasons listed above
            arca.run(temp_repo_func.url, temp_repo_func.branch, task)
