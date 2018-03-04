import os


if os.environ.get("TRAVIS", False):
    BASE_DIR = "/home/travis/build/{}/test_loc".format(os.environ.get("TRAVIS_REPO_SLUG", "mikicz/arca"))
else:
    BASE_DIR = "/tmp/arca/test"


def replace_text(path, text):
    with path.open("w") as fl:
        fl.write(text)


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

RETURN_DJANGO_VERSION_FUNCTION = """
import django

def return_str_function():
    return django.__version__
"""

RETURN_PYTHON_VERSION_FUNCTION = """
import sys

def return_python_version():
    return "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
"""

RETURN_IS_XSLTPROC_INSTALLED = """
import subprocess

def return_is_xsltproc_installed():
    try:
        return subprocess.Popen(["xsltpoc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).wait()
    except:
        return False
"""

RETURN_IS_LXML_INSTALLED = """
def return_is_lxml_installed():
    try:
        import lxml
        return True
    except:
        return False
"""

RETURN_PLATFORM = """
import platform

def return_platform():
    return platform.dist()[0]
"""
