# encoding=utf-8
import json
import os
from pathlib import Path

import pytest
from dogpile.cache.api import NO_VALUE

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
def test_cache(mocker, temp_repo_func, backend, cache_backend, arguments):
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

    requirements_path = temp_repo_func.path / "requirements.txt"
    requirements_path.write_text("django==1.11.5")

    temp_repo_func.repo.index.add([str(requirements_path)])
    temp_repo_func.repo.index.commit("Added requirements")

    django_task = Task("django:get_version")

    # delete from previous tests
    arca.region.delete(arca.cache_key(temp_repo_func.url, temp_repo_func.branch, django_task, temp_repo_func.repo))
    mocker.spy(arca.backend, "run")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, django_task).output == "1.11.5"
    assert arca.backend.run.call_count == 1

    cached_result = arca.region.get(
        arca.cache_key(temp_repo_func.url, temp_repo_func.branch, django_task, temp_repo_func.repo)
    )

    assert cached_result is not NO_VALUE

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, django_task).output == "1.11.5"

    # check that the result was actually from cache, that run wasn't called again
    assert arca.backend.run.call_count == 1

    arca.pull_again(temp_repo_func.url, temp_repo_func.branch)

    mocker.spy(arca, "get_files")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, django_task).output == "1.11.5"
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

    # in case ignore is set, no error thrown, region configred
    arca = Arca(base_dir=BASE_DIR,
                single_pull=True,
                ignore_cache_errors=True,
                settings={
                    "ARCA_CACHE_BACKEND": "dogpile.cache.dbm",
                    "ARCA_CACHE_BACKEND_ARGUMENTS": json.dumps({"filename": str(Path(BASE_DIR) / "cachefile.dbm")})[:-1]
                })

    assert arca.region.is_configured


def test_cache_backend_module_not_found():
    # redis must not be present in the env
    with pytest.raises(ImportError):
        import redis  # noqa

    with pytest.raises(ModuleNotFoundError):
        Arca(base_dir=BASE_DIR,
             single_pull=True,
             settings={
                 "ARCA_CACHE_BACKEND": "dogpile.cache.redis"
             })

    arca = Arca(base_dir=BASE_DIR,
                single_pull=True,
                ignore_cache_errors=True,
                settings={
                    "ARCA_CACHE_BACKEND": "dogpile.cache.redis"
                })

    assert arca.region.is_configured
