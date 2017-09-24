import importlib


def load_class(location: str) -> type:
    module_name = ".".join(location.split(".")[:-1])
    class_name = location.split(".")[-1]
    imported_module = importlib.import_module(module_name)

    try:
        return getattr(imported_module, class_name)
    except AttributeError:
        raise ValueError(f"{module_name} does not have a {class_name} class")  # TODO: custom exception?
