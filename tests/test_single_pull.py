from arca import Arca, Task, CurrentEnvironmentBackend
from common import SECOND_RETURN_STR_FUNCTION, BASE_DIR, TEST_UNICODE


def test_single_pull(temp_repo_func, mocker):
    backend = CurrentEnvironmentBackend(verbosity=2)
    arca = Arca(backend=backend, base_dir=BASE_DIR, single_pull=True)

    mocker.spy(arca, "_pull")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    temp_repo_func.file_path.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    arca.pull_again(temp_repo_func.url, temp_repo_func.branch)

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 2


def test_pull_efficiency(temp_repo_func, mocker):
    backend = CurrentEnvironmentBackend(verbosity=2)
    arca = Arca(backend=backend, base_dir=BASE_DIR)

    mocker.spy(arca, "_pull")

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 1

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
    assert arca._pull.call_count == 2

    temp_repo_func.file_path.write_text(SECOND_RETURN_STR_FUNCTION)
    temp_repo_func.repo.index.add([str(temp_repo_func.file_path)])
    temp_repo_func.repo.index.commit("Updated function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 3

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == TEST_UNICODE
    assert arca._pull.call_count == 4
