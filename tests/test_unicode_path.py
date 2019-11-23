from arca import Arca, Task, CurrentEnvironmentBackend
from common import BASE_DIR


def test_unicode_path(temp_repo_func,):
    backend = CurrentEnvironmentBackend(verbosity=2)
    arca = Arca(backend=backend, base_dir=BASE_DIR + "/abčď", single_pull=True)

    task = Task("test_file:return_str_function")

    assert arca.run(temp_repo_func.url, temp_repo_func.branch, task).output == "Some string"
