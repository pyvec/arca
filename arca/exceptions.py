

class ArcaException(Exception):
    """ A base exception from which all exceptions raised by Arca are subclassed.
    """


class ArcaMisconfigured(ValueError, ArcaException):
    """ An exception for all cases of misconfiguration.
    """

    PACKAGE_MISSING = "Couldn't import package '{}' that is required for this backend. " \
                      "Did you install the extra requirements for this backend?"


class TaskMisconfigured(ValueError, ArcaException):
    """ Raised if Task is incorrectly defined.
    """


class PullError(ArcaException):
    """ Raised if repository can't be cloned or pulled.
    """


class BuildError(ArcaException):
    """ Raised if the task fails.
    """

    def __init__(self, *args, extra_info=None, **kwargs):
        super().__init__(*args, **kwargs)

        #: Extra information what failed
        self.extra_info = extra_info

    def __str__(self):
        extra_info = self.extra_info
        if isinstance(extra_info, dict) and "traceback" in extra_info:
            extra_info = extra_info["traceback"]
        return "{}\n\n{}".format(
            super().__str__(),
            extra_info
        )


class BuildTimeoutError(BuildError):
    """ Raised if the task takes too long.
    """


class PushToRegistryError(ArcaException):
    """ Raised if pushing of images to Docker registry in :class:`DockerBackend` fails.
    """

    def __init__(self, *args, full_output=None, **kwargs):
        super().__init__(*args, **kwargs)

        #: Full output of the push command
        self.full_output = full_output

    def __str__(self):
        return "{}\n\n{}".format(
            super().__str__(),
            self.full_output
        )


class FileOutOfRangeError(ValueError, ArcaException):
    """
    Raised if ``relative_path`` in :meth:`Arca.static_filename <arca.Arca.static_filename>`
    leads outside the repository.
    """


class RequirementsMismatch(ValueError, ArcaException):
    """
    Raised if the target repository has extra requirements compared to the current environment
    if the ``requirements_strategy`` of
    :class:`CurrentEnvironmentBackend <arca.backends.CurrentEnvironmentBackend>`
    is set to :attr:`arca.backends.RequirementsStrategy.raise`.
    """

    def __init__(self, *args, diff=None, **kwargs):
        super().__init__(*args, **kwargs)

        #: The extra requirements
        self.diff = diff

    def __str__(self):
        return "{}\nDiff:\n{}".format(
            super().__str__(),
            self.diff
        )
