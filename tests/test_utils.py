from uuid import uuid4

from arca.utils import is_dirty, get_last_commit_modifying_files


def test_is_dirty(temp_repo_static):
    assert not is_dirty(temp_repo_static.repo)

    fl = temp_repo_static.path / str(uuid4())
    fl.touch()

    assert is_dirty(temp_repo_static.repo)

    fl.unlink()

    assert not is_dirty(temp_repo_static.repo)

    original_text = temp_repo_static.fl.read_text()

    temp_repo_static.fl.write_text(original_text + str(uuid4()))

    assert is_dirty(temp_repo_static.repo)

    temp_repo_static.fl.write_text(original_text)

    assert not is_dirty(temp_repo_static.repo)


def test_get_last_commit_modifying_files(temp_repo_static):
    first_file = temp_repo_static.fl
    first_hash = temp_repo_static.repo.head.object.hexsha

    second_file = temp_repo_static.path / "second_test_file.txt"
    second_file.touch()

    temp_repo_static.repo.index.add([str(second_file)])
    temp_repo_static.repo.index.commit("Second")

    second_hash = temp_repo_static.repo.head.object.hexsha

    assert get_last_commit_modifying_files(temp_repo_static.repo, first_file.name) == first_hash
    assert get_last_commit_modifying_files(temp_repo_static.repo, second_file.name) == second_hash
    assert get_last_commit_modifying_files(temp_repo_static.repo, first_file.name, second_file.name) == second_hash
