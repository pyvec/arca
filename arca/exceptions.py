

class ArcaException(Exception):
    pass


class ArcaMisconfigured(ValueError, ArcaException):
    pass


class TaskMisconfigured(ValueError, ArcaException):
    pass


class PullError(ArcaException):
    pass


class BuildError(ArcaException):

    def __init__(self, *args, extra_info=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_info = extra_info

    def __str__(self):
        return "{}\n\n{}".format(
            super().__str__(),
            self.extra_info
        )


class PushToRegistryError(ArcaException):

    def __init__(self, *args, full_output=None,  **kwargs):
        super().__init__(*args, **kwargs)
        self.full_output = full_output

    def __str__(self):
        return "{}\n\n{}".format(
            super().__str__(),
            self.full_output
        )


class FileOutOfRangeError(ValueError, ArcaException):
    pass


class RequirementsMismatch(ValueError, ArcaException):

    def __init__(self, *args, diff=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.diff = diff

    def __str__(self):
        return "{}\nDiff:\n{}".format(
            super().__str__(),
            self.diff
        )
