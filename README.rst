arca
====

.. image:: https://img.shields.io/travis/mikicz/arca.svg
   :target: https://travis-ci.org/mikicz/arca

.. image:: https://img.shields.io/codecov/c/github/mikicz/arca.svg
   :target: https://codecov.io/gh/mikicz/arca

.. image:: https://img.shields.io/pypi/v/arca.svg
   :target: https://pypi.python.org/pypi/arca

.. image:: https://img.shields.io/github/license/mikicz/arca.svg?style=flat
   :target: https://github.com/mikicz/arca/blob/master/LICENSE

Arca is a library for running Python scripts from git repositories in various states of isolation.
Arca can also cache the results of these scripts using `dogpile.cache <https://dogpilecache.readthedocs.io/en/latest/>`_.

Getting started
***************

Requirements
++++++++++++

* Python >= 3.6
* Internet connection


Optional requirements for certain backends, they need to be runnable by the user using the library:

* Docker
* Vagrant

Optional for some caching backends:

* Redis
* Memcached

Hello World
+++++++++++

To run a Hello World you'll only need the ``arca.Arca`` and ``arca.Task`` classes.
``Task`` is used for defining the task that's supposed to be run in the repositories.
``Arca`` takes care of all the settings and provides the basic API for running tasks.

Lets presume that we have a repository ``https://example.com/hello_word.git`` with branch ``master`` that contains a
file ``hello_world.py`` with function ``say_hello``. In that case you would use the following example to launch the function
in a isolated environment:

.. code-block:: python

  from arca import Arca, Task

  task = Task("hello_world:say_hello")
  arca = Arca()

  result = arca.run("https://example.com/hello_word.git", "master", task)

Result will be a ``arca.Result`` instance which currently only has one attribute ``output`` with the output of the function call.
Should running of the task fail, ``arca.exceptions.BuildError`` will be raised.

By default, the ``CurrentEnvironmentBackend`` is used to run tasks, which uses the python installation which is used to run
arca, launching the code in a subprocess. You can learn about using different backends bellow.

Configuring arca
****************

There are three ways to configure ``Arca``.

1. You can initialize the class and backends directly and set it's options via constructor arguments.
For example changing the base directory where repositories are cloned and other arca-related things are saved you would call Arca like this:

.. code-block:: python

  arca = Arca(base_dir=".custom_arca_dir")

This option is the most direct but it has one caveat - options set by this method cannot be overidden by the following methods.

2. You can pass a dict with settings. The keys are always uppercase and prefixed with ``ARCA_``.
For example the same setting as above would be written as:

.. code-block:: python

  arca = Arca(settings={
    "ARCA_BASE_DIR": ".custom_arca_dir"
  })

3. You can configure ``Arca`` with environ variables, with keys being the same as in the second method.
Environ variables override settings from the second method.

You can combine these methods as long as you remember that options explicitly specified in constructors
cannot be overridden by the settings and environ methods.

Backends
********

There are currently four different backends. They can also be initialized in few different ways, consistent with general settings.
You can use the ``ARCA_BACKEND`` setting or you can pass a ``backend`` keyword directly to ``Arca``.
This setting can be either a string, class or an instance. String is used to load the class and initialize the instance,
class is used to initialize and a instance is used as is. All the initializations shown bellow are equivalent, but again,
as mentioned above, the straight ``backend`` keyword cannot be overridden by settings or environ variables.

.. code-block:: python

  from arca import Arca, DockerBackend

  Arca(settings={"ARCA_BACKEND": "arca.backend.DockerBackend"})
  Arca(settings={"ARCA_BACKEND": DockerBackend})
  Arca(backend="arca.backend.DockerBackend")
  Arca(backend=DockerBackend)
  Arca(backend=DockerBackend())


Setting up backends is based on the same principle as setting up ``Arca``. You can either pass keyword arguments when initializing class
or you can use settings with the prefix ``ARCA_BACKEND_``. For example these two calls are equivalent:

.. code-block:: python

  from arca import Arca, DockerBackend

  Arca(settings={
    "ARCA_BACKEND": "arca.backend.DockerBackend",
    "ARCA_BACKEND_PYTHON_VERSION": "3.6.4"
  })
  Arca(backend=DockerBackend(python_version="3.6.4"))


There are two options common for all backends:

* **requirements_location**: Tells backends where they should look for requirements in the repositories, the default is ``requirements.txt``.
* **cwd**: Tells backends in which folder they should launch the code, default is the root folder of the repository.

Current Environment
+++++++++++++++++++

*arca.backend.CurrentEnvironmentBackend*

This backend is the default option, it runs the tasks with the same Python that's used to run arca in a subprocess.
There are two settings for this backend, to determine how the backend should treat requirements in the repositories.

* **current_environment_requirements**: a path to the requirements of the current environment, the default is ``requirements.txt``.
  ``None`` would indicate there are no requirements for the current environment.
* **requirements_strategy**: Which approach the backend should take. There are three, the default being ``raise``.

Requirements strategies:

* ``raise``: Raise an ``arca.exceptions.RequirementsMismatch`` if there are any extra requirements in the target repository.
* ``ignore``: Ignore any extra requirements.
* ``install_extra``: Install the requirements that are extra in the target repository as opposed to the current environment.

Virtual Environment
+++++++++++++++++++

*arca.backend.VenvBackend*

This backend uses the Python virtual environments to run the tasks. The environments are created from the Python
used to run Arca and they are shared between repositories that have the same exact requirement file.
The virtual environments are stored in folder ``venv`` in folder determined by the ``Arca`` ``base_dir`` setting, usually ``.arca``.

Docker
++++++

*arca.backend.DockerBackend*

This backend runs tasks in docker containers. To use this backend the user running Arca needs to be able to interact
with ``docker`` (see `documentation <https://docs.docker.com/install/linux/linux-postinstall/>`_).

This backend firstly creates an image with requirements and dependencies installed so the installation only runs one.
By default the images are based on `custom images <https://hub.docker.com/r/mikicz/arca/tags/>`_, which have Python
and several build tools pre-installed.
These images are based on ``alpine`` and use `pyenv <https://github.com/pyenv/pyenv>`_ to install Python.
You can specify you want to base your images on a different image with the ``inherit_image`` setting.

Once arca has an image with the requirements installed, it launches a container for each task and kills it when the task finishes.
This can be modify by setting ``keep_container_running`` to ``True``, then the container is not killed and can be used
by different tasks running from the same repository, branch and commit. This can save time on starting up containers before each task.
You can then kill the containers by calling ``DockerBackend`` method ``stop_containers``.

If you're using arca on a CI/CD tool or somewhere docker images are not kept long-term, you can setup pushing
images with the installed requirements and dependencies to a docker registry and they will be pulled next time instead
of building them each time. It's set using ``push_to_registry_name`` and you'll have to be logged in to docker
using ``docker login``.

Settings:

* **python_version**: What Python version should be used.
  In theory any of `these versions <https://github.com/pyenv/pyenv/tree/master/plugins/python-build/share/python-build>`_ could be used,
  but only CPython 3.6 has been tested. The default is the Python version of the current environment.
  This setting is ignored if ``inherit_image`` is set.
* **keep_container_running**: When ``True``, containers aren't killed once the task finishes. Default is ``False``.
* **apk_dependencies**: For some python libraries, system dependencies are required,
  for example ``libxml2-dev`` and ``libxslt-dev`` are needed for ``lxml``.
  With this settings you can specify a list of system dependencies that will be installed via alpine ``apk``.
  This setting is ignored if ``inherit_image`` is set since arca can't determine how to install requirements on an unknown system.
* **disable_pull**: Disable pulling prebuilt arca images from Docker Hub and build even the base images locally.
* **inherit_image**: If you don't wish to use the arca images you can specify what image should be used instead.
* **push_to_registry_name**: Pushes all built images with installed requirements and dependencies to docker registry with this name,
  tries to pull image from the registry before building it locally to save time.

Vagrant
+++++++

*arca.backend.VagrantBackend*

**This backend might be reworked completely, consider its API unstable.**

If you're extra paranoid you can use Vagrant to completely isolate the tasks.
This backend is actually a subclass of ``DockerBackend`` and uses docker in the VM to run the tasks. Currently the backend
works by building the image with requirements and dependencies locally and pushing it to registry
(``push_to_registry_name`` is required), spinning up a VM for each repository, pulling the image in the VM and running the task.
Docker and Vagrant must be runnable by the current user.

The backend inherits all the settings of ``DockerBackend`` except for ``keep_container_running`` and has these extra settings:

* **box**: Vagrant box used in the VM. Either has to have docker version >= 1.8 or not have docker at all, in which case
  it will be installed when spinning up the VM. The default is `ailispaw/barge <https://app.vagrantup.com/ailispaw/boxes/barge>`_.
* **provider**: Vagrant provider, default is ``virtualbox``. Visit `vagrant docs <https://www.vagrantup.com/docs/providers/>`_ for more.
* **quiet**: Tells Vagrant and Fabric (which is used to run the task in the VM) to be quiet. Default is ``True``. Vagrant and Docker output is
  logged in separate files for each run in a folder ``logs`` in the ``Arca`` ``base_dir``. The filename is logged in the arca logger (see bellow)
* **destroy**: Destroy the VM right after the task is finished if ``True`` (default). If ``False`` is set, the VM is only halted.

Your own
++++++++

You can also create your own backend and pass it to ``Arca``. It has be a subclass of ``arca.backend.base.BaseBackend`` and
it has to implement its ``run`` method.

Other options and functionality
*******************************

Static files
++++++++++++

With method ``static_filename`` you can request a file from a repository.
The method accepts a relative path (can be a ``pathlib.Path`` or ``str``) to the file in the repository
and it returns an absolute path to the file is currently stored. The method raises ``arca.exceptions.FileOutOfRangeError``
when the relative path goes outside the scope of the repository and ``FileNotFoundError`` if the file doesn't exist in the
repository.

Singe pull
++++++++++

You might not want the repositories to be pulled everytime ``run`` is called.
You can specify that you want each repository and branch combination should be pulled only once
per initialization of ``Arca`` with the ``ARCA_SINGLE_PULL`` setting or ``single_pull`` keyword argument.

You can tell ``Arca`` to pull again by calling the method ``pull_again``.

Caching
+++++++

Arca can cache results of the tasks using ``dogpile.cache``. The default cache backend is ``dogpile.cache.null``, so no caching.
You can setup caching with the backend setting ``ARCA_CACHE_BACKEND`` and all the arguments needed for setup can be set
using ``ARCA_CACHE_BACKEND_ARGUMENTS`` which can either be a dict or or a json string.

Example setup:

.. code-block:: python

    arca = Arca(settings={
        "ARCA_CACHE_BACKEND": "dogpile.cache.redis",
        "ARCA_CACHE_BACKEND_ARGUMENTS": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
    })

To see all available cache backends and their settings,
please visit the ``dogpile.cache`` `documentation <https://dogpilecache.readthedocs.io/en/latest/>`_.

When ``Arca`` is being initialized, a check is made if the cache backend is writable and readable,
which raises an ``arca.exceptions.ArcaMisconfigured`` if it's not.
If you wish to ignore this error, set ``ARCA_IGNORE_CACHE_ERRORS`` to True or initialize ``Arca``  with ``ignore_cache_errors`` keyword argument.

Logging
+++++++

Arca logs debug information via standard Python logging. The logger is called ``arca``.

Running tests
**************

To run tests you'll need the optional requirements, Docker and Vagrant. Once you have them and they can be used by
the current user you just need to run:

.. code-block:: bash

  python setup.py test

This will launch the tests and a PEP8 check. The tests will take some time since building the custom
docker images is also tested and vagrant, in general, takes a long time to set up.

Contributing
************

I am developing this library as my bachelor thesis and will be not accepting any PRs at the moment.

Links
*****

- Repository: `GitHub <https://github.com/mikicz/arca>`_
- PyPi package: `arca <https://pypi.python.org/pypi/arca>`_
- CI: `Travis <https://travis-ci.org/mikicz/arca>`_
- Test coverage: `Codecov <https://codecov.io/gh/mikicz/arca>`_

License
*******

This project is licensed under the MIT License - see the `LICENSE <LICENSE>`_ file for details.
