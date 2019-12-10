import os
import shutil

import pytest
try:
    import vagrant
except ImportError:
    vagrant = None

from arca import VagrantBackend, Arca, Task
from arca.exceptions import ArcaMisconfigured, BuildTimeoutError
from common import BASE_DIR, RETURN_COLORAMA_VERSION_FUNCTION, SECOND_RETURN_STR_FUNCTION, TEST_UNICODE, \
    WAITING_FUNCTION


TEST_REGISTRY = "docker.io/arcaoss/arca-test"


@pytest.mark.skipif(vagrant is None, reason="Vagrant not installed.")
@pytest.mark.skipif(os.environ.get("TRAVIS", "false") == "true", reason="Vagrant doesn't work on Travis")
def test_validation():
    backend = VagrantBackend()

    # VagrantBackend requires `push_to_registry`
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # validation passes
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY)
    Arca(backend=backend)

    # push must be enabled
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY, registry_pull_only=True)
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # valid different box
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY, box="hashicorp/precise64")
    assert Arca(backend=backend).backend.box == "hashicorp/precise64"

    # invalid box
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY, box="ubuntu rusty64\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # valid different provider
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY, provider="vmware_fusion")
    assert Arca(backend=backend).backend.provider == "vmware_fusion"

    # invalid provider
    backend = VagrantBackend(use_registry_name=TEST_REGISTRY, provider="libvirst\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)


# `hashicorp/boot2docker` could be used to test that the backend fails when the box has old docker (1.7),
# but it takes a lot of time to download it and to spool it up, it does not make sense to use it.
# Also a nonexistant box could be tested if it raises an exception.
# If you want to test that even init of the VM works, set ``destroy`` to True, it will destroy the previous one as well.
# Set to ``False`` by default to bootup time and bandwidth.
@pytest.mark.skipif(vagrant is None, reason="Vagrant not installed.")
@pytest.mark.skipif(os.environ.get("TRAVIS", "false") == "true", reason="Vagrant doesn't work on Travis")
def test_vagrant(temp_repo_func, destroy=False):
    backend = VagrantBackend(verbosity=2, use_registry_name=TEST_REGISTRY,
                             keep_vm_running=True)
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    if destroy:
        vagrant_location = backend.get_vm_location()
        if vagrant_location.exists():
            vagrant_instance = vagrant.Vagrant(vagrant_location)
            vagrant_instance.destroy()
        shutil.rmtree(vagrant_location)

    # master branch - return colorama version
    temp_repo_func.file_path.write_text(RETURN_COLORAMA_VERSION_FUNCTION)
    requirements_path = temp_repo_func.repo_path / backend.requirements_location
    requirements_path.write_text("colorama==0.3.9")
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path), str(requirements_path)])
    temp_repo_func.repo.index.commit("Initial")

    # branch branch - return unicode
    temp_repo_func.repo.create_head("branch")
    temp_repo_func.repo.branches.branch.checkout()
    temp_repo_func.file_path.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Test unicode on a separate branch")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    # halt the VM, checks that the VM can be booted when stopped with the vagrant attribute set
    backend.stop_vm()
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    # halt the vm and create a new instance of the backend, to check that the vagrant attribute can be set from existing
    backend.stop_vm()
    backend = VagrantBackend(verbosity=2, use_registry_name=TEST_REGISTRY,
                             keep_vm_running=True)
    arca = Arca(backend=backend, base_dir=BASE_DIR)
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"

    # test that two branches can work next to each other
    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "0.3.9"
    assert arca.run(temp_repo_func.url, "branch", task).output == TEST_UNICODE

    # test timeout
    temp_repo_func.repo.branches[temp_repo_func.branch].checkout()
    temp_repo_func.file_path.write_text(WAITING_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Waiting function")

    task_1_second = Task("test_file:return_str_function", timeout=1)
    task_3_seconds = Task("test_file:return_str_function", timeout=3)

    with pytest.raises(BuildTimeoutError):
        assert arca.run(temp_repo_func.url, temp_repo_func.branch, task_1_second).output == "Some string"

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task_3_seconds).output == "Some string"

    backend.stop_vm()

    if destroy:
        backend.destroy = True
        backend.stop_vm()
