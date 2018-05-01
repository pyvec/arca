import os


if os.environ.get("TRAVIS", False):
    BASE_DIR = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
else:
    BASE_DIR = "/tmp/arca/test"


RETURN_STR_FUNCTION = """
def return_str_function():
    return "Some string"
"""

TEST_UNICODE = "Nechť již hříšné saxofony ďáblů rozezvučí síň úděsnými tóny waltzu, tanga a\xa0quickstepu.→"

SECOND_RETURN_STR_FUNCTION = f"""
def return_str_function():
    return "{TEST_UNICODE}"
"""

ARG_STR_FUNCTION = """
def return_str_function(arg):
    return arg[::-1]
"""

KWARG_STR_FUNCTION = """
def return_str_function(*, kwarg):
    return kwarg[::-1]
"""

RETURN_COLORAMA_VERSION_FUNCTION = """
import colorama

def return_str_function():
    return colorama.__version__
"""

RETURN_PYTHON_VERSION_FUNCTION = """
import platform

def return_python_version():
    return platform.python_version()
"""

RETURN_ALSAAUDIO_INSTALLED = """
import alsaaudio

def return_alsaaudio_installed():
    return alsaaudio is not None
"""

RETURN_PLATFORM = """
import platform

def return_platform():
    return platform.dist()[0]
"""
