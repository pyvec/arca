from pathlib import Path
from uuid import uuid4

import os
import pytest
from git import Repo

from arca import VagrantBackend, Arca, Task
from arca.exceptions import ArcaMisconfigured, BuildError
from common import BASE_DIR, RETURN_DJANGO_VERSION_FUNCTION


def test_validation():
    """ These tests work on Travis
    """
    backend = VagrantBackend()

    # VagrantBackend requires `push_to_registry`
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # validation passes
    backend = VagrantBackend(push_to_registry_name="docker.io/mikicz/arca-test")
    Arca(backend=backend)

    # valid different box
    backend = VagrantBackend(push_to_registry_name="docker.io/mikicz/arca-test", box="hashicorp/precise64")
    assert Arca(backend=backend).backend.box == "hashicorp/precise64"

    # invalid box
    backend = VagrantBackend(push_to_registry_name="docker.io/mikicz/arca-test", box="ubuntu rusty64\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)

    # valid different provider
    backend = VagrantBackend(push_to_registry_name="docker.io/mikicz/arca-test", provider="vmware_fusion")
    assert Arca(backend=backend).backend.provider == "vmware_fusion"

    # invalid provider
    backend = VagrantBackend(push_to_registry_name="docker.io/mikicz/arca-test", provider="libvirst\"")
    with pytest.raises(ArcaMisconfigured):
        Arca(backend=backend)


# `hashicorp/boot2docker` contains docker 1.7 - doesn't work
# `asdfkljasdf/asdfasdf` doesn't exist
@pytest.mark.parametrize("box", [None, "hashicorp/boot2docker", "asdfkljasdf/asdfasdf"])
def test_vagrant(box):
    if os.environ.get("TRAVIS", False):
        pytest.skip("Vagrant doesn't work on Travis")

    kwargs = {}
    if box:
        kwargs["box"] = box
    backend = VagrantBackend(verbosity=2, push_to_registry_name="docker.io/mikicz/arca-test", **kwargs)
    arca = Arca(backend=backend, base_dir=BASE_DIR)
    git_dir = Path("/tmp/arca/") / str(uuid4())
    git_repo = Repo.init(git_dir)

    filepath = git_dir / "test_file.py"
    filepath.write_text(RETURN_DJANGO_VERSION_FUNCTION)
    git_repo.index.add([str(filepath)])

    requirements_path = git_dir / backend.requirements_location
    requirements_path.parent.mkdir(exist_ok=True, parents=True)
    with requirements_path.open("w") as fl:
        fl.write("django==1.11.3")  # Has to be unique in Arca tests.
    git_repo.index.add([str(requirements_path)])

    git_repo.index.commit("Initial")

    task = Task(
        "test_file:return_str_function",
    )

    repo = f"file://{git_dir}"
    branch = "master"

    if not box:
        result = arca.run(repo, branch, task)
        assert result.output == "1.11.3"
    else:
        with pytest.raises(BuildError):  # fails because of reasons listed above
            arca.run(repo, branch, task)
