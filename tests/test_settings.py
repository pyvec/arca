# encoding=utf-8
import os
import pytest

from arca import Arca, RequirementsStrategy
from arca.utils import Settings


def test_settings():
    settings = Settings({"ARCA_TEST_ONE": 1, "ARCA_TEST_TWO": 2})

    assert settings.get("test_one") == 1
    assert settings.get("test_two") == 2
    assert settings.get("test_non", "test_one") == 1
    assert settings.get("test_one", "test_two") == 1
    assert settings.get("test_two", "test_one") == 2

    with pytest.raises(Exception):
        settings.get()

    with pytest.raises(KeyError):
        settings.get("test_non")

    with pytest.raises(KeyError):
        settings.get("test_non", "test_non_two")


def test_setting_integration():
    arca = Arca(settings={
        "ARCA_BACKEND": "arca.backend.CurrentEnvironmentBackend",
        "ARCA_CURRENT_ENVIRONMENT_BACKEND_REQUIREMENTS_STRATEGY": "ignore",
        "ARCA_BACKEND_REQUIREMENTS_STRATEGY": "install_extra",
        "ARCA_BACKEND_CWD": "test/"
    })

    assert arca.backend.requirements_strategy == RequirementsStrategy.IGNORE  # specific backend setting
    assert arca.backend.cwd == "test/"  # tests generic BACKEND settings
    assert arca.backend.requirements_location == "requirements.txt"  # tests default value


def test_environ():
    os.environ["ARCA_TEST_ONE"] = "test"
    os.environ["ARCA_TEST_THREE"] = "test3"
    os.environ["ACRA_TEST_FOUR"] = "test4"

    arca = Arca(settings={"ARCA_TEST_ONE": 1, "ARCA_TEST_TWO": 2})

    assert arca.settings.get("test_one") == "test"
    assert arca.settings.get("test_three") == "test3"
    with pytest.raises(KeyError):
        arca.settings.get("test_four")
