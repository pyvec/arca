# encoding=utf-8
import pytest

from arca import Arca, VenvBackend


def test_arca_backend():
    assert isinstance(Arca(VenvBackend()).backend, VenvBackend)
    assert isinstance(Arca(VenvBackend).backend, VenvBackend)
    assert isinstance(Arca("arca.backend.VenvBackend").backend, VenvBackend)

    with pytest.raises(ModuleNotFoundError):
        Arca("arca.backend_test.TestBackend")

    with pytest.raises(ValueError):
        Arca("arca.backend.TestBackend")

    class NotASubclassClass:
        pass

    with pytest.raises(ValueError):
        Arca(NotASubclassClass)

    with pytest.raises(ValueError):
        Arca(NotASubclassClass)
