# encoding=utf-8
import json
from pathlib import Path
from uuid import uuid4

import os

import pytest
from dogpile.cache.api import NO_VALUE
from git import Repo

from arca import Arca, VenvBackend, Task


@pytest.mark.skipif(bool(os.environ.get("TRAVIS", False)), reason="Venv backend doesn't work on Travis")
@pytest.mark.parametrize(["cache_backend", "arguments"], [
    ("dogpile.cache.dbm", lambda base_dir: {
        "filename": str(base_dir / "cachefile.dbm")
    }),
    ("dogpile.cache.dbm", lambda base_dir: json.dumps({
        "filename": str(base_dir / "cachefile.dbm")
    })),
    ('dogpile.cache.memory', lambda base_dir: None),
    ('dogpile.cache.memory_pickle', lambda base_dir: None),
])
def test_cache(mocker, cache_backend, arguments):
    if os.environ.get("TRAVIS", False):
        base_dir = Path("/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca")))
    else:
        base_dir = Path("/tmp/arca/test")

    backend = VenvBackend(base_dir=base_dir, verbosity=2, single_pull=True)

    base_dir.mkdir(parents=True, exist_ok=True)

    arca = Arca(backend=backend, settings={
        "ARCA_CACHE_BACKEND": cache_backend,
        "ARCA_CACHE_BACKEND_ARGUMENTS": arguments(base_dir)
    })

    git_dir = Path("/tmp/arca/") / str(uuid4())

    repo = Repo.init(git_dir)
    requirements_path = git_dir / "requirements.txt"
    requirements_path.parent.mkdir(exist_ok=True, parents=True)

    with requirements_path.open("w") as fl:
        fl.write("django==1.11.5")

    repo.index.add([str(requirements_path)])
    repo.index.commit("Added requirements")

    django_task = Task(
        "django.get_version",
        imports=["django"]
    )

    arca.region.delete(arca.cache_key(f"file://{git_dir}", "master", django_task))  # delete from previous tests
    mocker.spy(arca.backend, "run")

    repo = f"file://{git_dir}"
    branch = "master"

    result = arca.run(repo, branch, django_task)

    try:
        print(result.error)
    except AttributeError:
        pass

    assert result.success
    assert result.result == "1.11.5"

    assert arca.backend.run.call_count == 1

    cached_result = arca.region.get(
        arca.cache_key(repo, branch, django_task)
    )

    assert cached_result is not NO_VALUE

    result = arca.run(repo, branch, django_task)
    assert result.success
    assert result.result == "1.11.5"

    # check that the result was actually from cache, that run wasn't called again
    assert arca.backend.run.call_count == 1

    arca.pull_again(repo, branch)

    mocker.spy(arca.backend, "update_environment")

    result = arca.run(repo, branch, django_task)
    assert result.success
    assert result.result == "1.11.5"

    assert arca.backend.update_environment.call_count == 1  # check that the repo was pulled
