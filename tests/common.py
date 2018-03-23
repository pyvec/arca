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

SECOND_RETURN_STR_FUNCTION = """
def return_str_function():
    return "Nechť již hříšné saxofony ďáblů rozezvučí síň úděsnými tóny waltzu, tanga a\xa0quickstepu.→"
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
import sys

def return_python_version():
    return "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
"""

RETURN_FREETYPE_VERSION = """
import freetype

def return_freetype_version():
    return freetype.version()
"""

RETURN_PLATFORM = """
import platform

def return_platform():
    return platform.dist()[0]
"""
