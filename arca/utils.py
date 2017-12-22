import importlib
import logging
from typing import Any, Dict, Optional

NOT_SET = object()
logger = logging.getLogger("arca")
logger.setLevel(logging.DEBUG)


def load_class(location: str) -> type:
    module_name = ".".join(location.split(".")[:-1])
    class_name = location.split(".")[-1]
    imported_module = importlib.import_module(module_name)

    try:
        return getattr(imported_module, class_name)
    except AttributeError:
        raise ValueError(f"{module_name} does not have a {class_name} class")  # TODO: custom exception?


class LazySettingProperty:
    def __init__(self, *, key, default=NOT_SET) -> None:
        self.key = key
        self.default = default

    def __set_name__(self, cls, name):
        self.name = name

    def __get__(self, instance, cls):
        if instance is None or (hasattr(instance, "_arca") and instance._arca is None):
            return self
        result = instance.get_setting(self.key, self.default)
        setattr(instance, self.name, result)
        return result


class Settings:

    PREFIX = "ARCA"

    def __init__(self, data: Optional[Dict[str, Any]]=None) -> None:
        self.data = data or {}

    def get(self, *options: str, default: Any=NOT_SET) -> Any:
        if not len(options):
            raise ValueError("At least one key must be provided.")

        for option in options:
            key = f"{self.PREFIX}_{option.upper()}"
            if key in self:
                return self[key]

        if default is NOT_SET:
            raise KeyError("None of the following key is present in settings and no default is set: {}".format(
                ", ".join(options)
            ))

        return default

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __contains__(self, item):
        return item in self.data
