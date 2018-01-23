# encoding=utf-8
import json
from pathlib import Path
from uuid import uuid4

import os

import pytest
from dogpile.cache.api import NO_VALUE
from git import Repo

from arca import Arca, VenvBackend, Task, DockerBackend, CurrentEnvironmentBackend
from arca.exceptions import ArcaMisconfigured

from common import BASE_DIR


cache_arguments = [
    ["dogpile.cache.dbm", lambda base_dir: {"filename": str(base_dir / "cachefile.dbm")}],
    ["dogpile.cache.dbm", lambda base_dir: json.dumps({"filename": str(base_dir / "cachefile.dbm")})],
    ['dogpile.cache.memory', lambda base_dir: None],
    ['dogpile.cache.memory_pickle', lambda base_dir: None],
]


def generate_arguments():
    for backend in [VenvBackend, DockerBackend, CurrentEnvironmentBackend]:
        for arguments in cache_arguments:
            yield tuple([backend] + arguments)


@pytest.mark.parametrize(["backend", "cache_backend", "arguments"], list(generate_arguments()))
def test_cache(mocker, backend, cache_backend, arguments):
    if backend == VenvBackend and bool(os.environ.get("TRAVIS", False)):
        pytest.skip("Venv backend doesn't work on Travis")

    base_dir = Path(BASE_DIR)

    kwargs = {}
    if backend == CurrentEnvironmentBackend:
        kwargs["current_environment_requirements"] = None
        kwargs["requirements_strategy"] = "install_extra"

    backend = backend(verbosity=2, **kwargs)

    base_dir.mkdir(parents=True, exist_ok=True)

    arca = Arca(backend=backend,
                base_dir=BASE_DIR,
                single_pull=True,
                settings={
                    "ARCA_CACHE_BACKEND": cache_backend,
                    "ARCA_CACHE_BACKEND_ARGUMENTS": arguments(base_dir)
                })

    git_dir = Path("/tmp/arca/") / str(uuid4())

    git_repo = Repo.init(git_dir)
    requirements_path = git_dir / "requirements.txt"
    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.5")

    git_repo.index.add([str(requirements_path)])
    git_repo.index.commit("Added requirements")

    django_task = Task(
        "django.get_version",
        imports=["django"]
    )

    repo = f"file://{git_dir}"
    branch = "master"

    arca.region.delete(arca.cache_key(repo, branch, django_task, git_repo))  # delete from previous tests
    mocker.spy(arca.backend, "run")

    result = arca.run(repo, branch, django_task)

    assert result.output == "1.11.5"

    assert arca.backend.run.call_count == 1

    cached_result = arca.region.get(
        arca.cache_key(repo, branch, django_task, git_repo)
    )

    assert cached_result is not NO_VALUE

    result = arca.run(repo, branch, django_task)
    assert result.output == "1.11.5"

    # check that the result was actually from cache, that run wasn't called again
    assert arca.backend.run.call_count == 1

    arca.pull_again(repo, branch)

    mocker.spy(arca, "get_files")

    result = arca.run(repo, branch, django_task)
    assert result.output == "1.11.5"

    assert arca.get_files.call_count == 1  # check that the repo was pulled

    if isinstance(backend, CurrentEnvironmentBackend):
        backend._uninstall("django")


def test_invalid_arguments():
    with pytest.raises(ArcaMisconfigured):
        Arca(base_dir=BASE_DIR,
             single_pull=True,
             settings={
                 "ARCA_CACHE_BACKEND": "dogpile.cache.dbm",
                 "ARCA_CACHE_BACKEND_ARGUMENTS": json.dumps({"filename": str(Path(BASE_DIR) / "cachefile.dbm")})[:-1]
             })
