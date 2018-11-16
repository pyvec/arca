#!/usr/bin/env python3
# encoding=utf-8
import sys
from pathlib import Path

from setuptools import setup, find_packages

from utils import DeployDockerBasesCommand

if sys.version_info < (3, 6):
    raise RuntimeError('Arca requires Python 3.6 or greater')


def long_description():
    return """{}\n\n{}""".format(
        (Path(__file__).resolve().parent / "README.rst").read_text().split(".. split_here")[0],
        (Path(__file__).resolve().parent / "docs/changes.rst").read_text()
    )


setup(
    name="arca",
    version="0.3.1",
    author="Mikuláš Poul",
    author_email="mikulaspoul@gmail.com",
    description="A library for running Python functions (callables) from git repositories "
                "in various states of isolation with integrating caching.",
    keywords=["sandboxing", "git", "docker", "vagrant"],
    license="MIT",
    url="https://github.com/mikicz/arca",
    packages=find_packages(),
    long_description=long_description(),
    install_requires=[
        "gitpython==2.1.9",
        "dogpile.cache==0.6.5",
        "requests",
        "entrypoints>=0.2.3",
        "cached-property",
    ],
    extras_require={
        "docker": [
            "docker~=3.2.1",
        ],
        "vagrant": [
            "docker~=3.2.1",
            "python-vagrant",
            "fabric3",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Security",
        "Topic :: Utilities",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Software Development :: Version Control :: Git"
    ],
    setup_requires=["pytest-runner"],
    tests_require=["pytest", "pytest-flake8", "pytest-cov", "pytest-mock"],
    cmdclass={
        "deploy_docker_bases": DeployDockerBasesCommand
    },
    project_urls={
        "Documentation": "https://arca.readthedocs.io/",
        "CI": "https://travis-ci.org/mikicz/arca",
        "Test coverage": "https://codecov.io/gh/mikicz/arca",
    },
)
