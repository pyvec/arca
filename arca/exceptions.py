

class ArcaException(Exception):
    pass


class ArcaMisconfigured(ArcaException):
    pass


class TaskMisconfigured(ValueError, ArcaException):
    pass


class BuildError(ArcaException):

    def __init__(self, *args, extra_info=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_info = extra_info


class PushToRegistryError(ArcaException):

    def __init__(self, *args, full_output=None,  **kwargs):
        super().__init__(*args, **kwargs)
        self.full_output = full_output