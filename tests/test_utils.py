from uuid import uuid4

from arca.utils import is_dirty, get_last_commit_modifying_files, get_hash_for_file


def test_is_dirty(temp_repo_static):
    assert not is_dirty(temp_repo_static.repo)

    fl = temp_repo_static.repo_path / str(uuid4())
    fl.touch()

    assert is_dirty(temp_repo_static.repo)

    fl.unlink()

    assert not is_dirty(temp_repo_static.repo)

    original_text = temp_repo_static.file_path.read_text()

    temp_repo_static.file_path.write_text(original_text + str(uuid4()))

    assert is_dirty(temp_repo_static.repo)

    temp_repo_static.file_path.write_text(original_text)

    assert not is_dirty(temp_repo_static.repo)


def test_get_last_commit_modifying_files(temp_repo_static):
    first_file = temp_repo_static.file_path
    first_hash = temp_repo_static.repo.head.object.hexsha

    second_file = temp_repo_static.repo_path / "second_test_file.txt"
    second_file.touch()

    temp_repo_static.repo.index.add([str(second_file)])
    temp_repo_static.repo.index.commit("Second")

    second_hash = temp_repo_static.repo.head.object.hexsha

    assert get_last_commit_modifying_files(temp_repo_static.repo, first_file.name) == first_hash
    assert get_last_commit_modifying_files(temp_repo_static.repo, second_file.name) == second_hash
    assert get_last_commit_modifying_files(temp_repo_static.repo, first_file.name, second_file.name) == second_hash


def test_get_hash_for_file(temp_repo_static):
    file_hash = get_hash_for_file(temp_repo_static.repo, temp_repo_static.file_path.name)

    temp_repo_static.file_path.write_text(str(uuid4()))

    temp_repo_static.repo.index.add([str(temp_repo_static.file_path)])
    temp_repo_static.repo.index.commit("Updated")

    assert get_hash_for_file(temp_repo_static.repo, temp_repo_static.file_path.name) != file_hash
