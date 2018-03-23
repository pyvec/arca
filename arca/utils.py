import importlib
import logging
from typing import Any, Dict, Optional, Callable

from git import Repo

from .exceptions import ArcaMisconfigured


class NotSet:
    """ For default values which can't be ``None``.
    """
    def __repr__(self):
        return "NOT_SET"

    def __str__(self):
        return "NOT_SET"


NOT_SET = NotSet()

logger = logging.getLogger("arca")
logger.setLevel(logging.DEBUG)


def load_class(location: str) -> type:
    """ Loads a class from a string and returns it

    :raise ArcaMisconfigured: If the class can't be loaded.

    >>> from arca.utils import load_class
    >>> load_class("arca.backend.BaseBackend")
    <class 'arca.backend.base.BaseBackend'>
    """
    module_name = ".".join(location.split(".")[:-1])
    class_name = location.split(".")[-1]

    try:
        imported_module = importlib.import_module(module_name)
        return getattr(imported_module, class_name)
    except ModuleNotFoundError:
        raise ArcaMisconfigured(f"{module_name} does not exist.")
    except AttributeError:
        raise ArcaMisconfigured(f"{module_name} does not have a {class_name} class")


class LazySettingProperty:
    """
    For defining properties for the :class:`Arca` class and for the backends.
    The property is evaluated lazily when accessed, getting the value from settings
    using the instances method ``get_setting``. The property can be overridden by the constructor.
    """
    def __init__(self, *, key, default=NOT_SET, convert: Callable=None) -> None:
        self.key = key
        self.default = default
        self.convert = convert

    def __set_name__(self, cls, name):
        self.name = name

    def __get__(self, instance, cls):
        if instance is None or (hasattr(instance, "_arca") and instance._arca is None):
            return self
        result = instance.get_setting(self.key, self.default)

        if self.convert is not None:
            result = self.convert(result)

        setattr(instance, self.name, result)
        return result


class Settings:
    """ A wrapper around dict for handling :class:`Arca <arca.Arca>` settings.
    """

    PREFIX = "ARCA"

    def __init__(self, data: Optional[Dict[str, Any]]=None) -> None:
        self.data = data or {}

    def get(self, *keys: str, default: Any = NOT_SET) -> Any:
        """ Returns values from the settings in the order of keys, the first value encountered is used.

        Example:

        >>> settings = Settings({"ARCA_ONE": 1, "ARCA_TWO": 2})
        >>> settings.get("one")
        1
        >>> settings.get("one", "two")
        1
        >>> settings.get("two", "one")
        2
        >>> settings.get("three", "one")
        1
        >>> settings.get("three", default=3)
        3
        >>> settings.get("three")
        Traceback (most recent call last):
        ...
        KeyError:

        :param keys: One or more keys to get from settings. If multiple keys are provided, the value of the first key
            that has a value is returned.
        :param default: If none of the ``options`` aren't set, return this value.
        :return: A value from the settings or the default.

        :raise ValueError: If no keys are provided.
        :raise KeyError: If none of the keys are set and no default is provided.

        """
        if not len(keys):
            raise ValueError("At least one key must be provided.")

        for option in keys:
            key = f"{self.PREFIX}_{option.upper()}"
            if key in self:
                return self[key]

        if default is NOT_SET:
            raise KeyError("None of the following key is present in settings and no default is set: {}".format(
                ", ".join(keys)
            ))

        return default

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __contains__(self, item):
        return item in self.data


def is_dirty(repo: Repo) -> bool:
    """ Returns if the ``repo`` has been modified (including untracked files).
    """
    return repo.is_dirty(untracked_files=True)


def get_last_commit_modifying_files(repo: Repo, *files) -> str:
    """ Returns the hash of the last commit which modified some of the files (or files in those folders).

    :param repo: The repo to check in.
    :param files: List of files to check
    :return: Commit hash.
    """
    return repo.git.log(*files, n=1, format="%H")
