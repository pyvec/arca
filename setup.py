#!/usr/bin/env python3
# encoding=utf-8
import sys
from pathlib import Path

from setuptools import setup, find_packages

from utils import DeployDockerBasesCommand

if sys.version_info < (3, 6):
    raise RuntimeError('Arca requires Python 3.6 or greater')


def read(filename: str) -> str:
    return (Path(__file__).resolve().parent / filename).read_text()


setup(
    name="arca",
    version="0.0.4",
    author="Mikuláš Poul",
    author_email="mikulaspoul@gmail.com",
    description="A tool to launch possibly dangerous code from different git repositories in a isolated environment",
    # keywords=[""],  # TODO
    license="MIT",
    url="https://github.com/mikicz/arca",
    packages=find_packages(),
    long_description=read("README.rst"),
    install_requires=[
        "gitpython==2.1.7",
        "dogpile.cache==0.6.4",
        "requests",
        "docker",
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",  # TODO: update when ready
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
    }
)
