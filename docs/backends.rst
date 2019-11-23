.. _backends:

Backends
========

There are currently four different backends. They can also be initialized in few different ways,
consistent with general settings. You can use the ``ARCA_BACKEND`` setting
or you can pass a ``backend`` keyword directly to :class:`Arca <arca.Arca>`.

The backend setting can be either a string, class or an instance. All the initializations shown bellow are equivalent,
but again, as mentioned in :ref:`configuring`, the ``backend`` keyword cannot be overridden by settings
or environ variables.

.. code-block:: python

  from arca import Arca, DockerBackend

  Arca(settings={"ARCA_BACKEND": "arca.backend.DockerBackend"})
  Arca(settings={"ARCA_BACKEND": DockerBackend})
  Arca(backend="arca.backend.DockerBackend")
  Arca(backend=DockerBackend)
  Arca(backend=DockerBackend())


Setting up backends is based on the same principle as setting up :class:`Arca <arca.Arca>`.
You can either pass keyword arguments when initializing the backend class
or you can use settings (described in more details in :ref:`configuring`). For example these two calls are equivalent:

.. code-block:: python

  from arca import Arca, DockerBackend

  Arca(settings={
    "ARCA_BACKEND": "arca.backend.DockerBackend",
    "ARCA_BACKEND_PYTHON_VERSION": "3.6.4"
  })
  Arca(backend=DockerBackend(python_version="3.6.4"))

As mentioned in :ref:`options`, there are two options common for all backends. (See that section for more details.)

* **requirements_location**
* **requirements_timeout**
* **pipfile_location**
* **cwd**

.. _backends_cur:

Current Environment
-------------------

*arca.backend.CurrentEnvironmentBackend*

This backend is the default option, it runs the tasks with the same Python that's used to run Arca, in a subprocess.
There are no extra settings for this backend. All the requirements in repositories are ignored completely.

(possible settings prefixes: ``ARCA_CURRENT_ENVIRONMENT_BACKEND_`` and ``ARCA_BACKEND_``)

.. _backends_venv:

Virtual Environment
-------------------

*arca.backend.VenvBackend*

This backend uses the Python virtual environments to run the tasks. The environments are created from the Python
used to run Arca and they are shared between repositories that have the same exact requirement file.
The virtual environments are stored in folder ``venv`` in folder
determined by the :class:`Arca <arca.Arca>` ``base_dir`` setting, usually ``.arca``.

For installing requirements using Pipenv it must be available to be launched by the current user.
Disabling Pipenv can be done by setting the **pipfile_location** to ``None``.

(possible settings prefixes: ``ARCA_VENV_BACKEND_`` and ``ARCA_BACKEND_``)

.. _backends_doc:

Docker
------

*arca.backend.DockerBackend*

This backend runs tasks in docker containers. To use this backend the user running Arca needs to be able to interact
with ``docker`` (see `documentation <https://docs.docker.com/install/linux/linux-postinstall/>`_).

This backend first creates an image with requirements and dependencies installed so the installation only runs once.
By default the images are based on `custom images <https://hub.docker.com/r/arcaoss/arca/tags/>`_, which have Python
and several build tools pre-installed.
These images are based on ``debian`` (slim ``stretch`` version) and use `pyenv <https://github.com/pyenv/pyenv>`_
to install Python.
You can specify you want to base your images on a different image with the ``inherit_image`` setting.

Once Arca has an image with the requirements installed, it launches a container for each task and
kills it when the task finishes. This can be modify by setting ``keep_container_running`` to ``True``,
then the container is not killed and can be used by different tasks running from the same repository, branch and commit.
This can save time on starting up containers before each task.
You can then kill the containers by calling ``DockerBackend`` method ``stop_containers``.

If you're using Arca on a CI/CD tool or somewhere docker images are not kept long-term, you can setup pushing
images with the installed requirements and dependencies to a docker registry and they will be pulled next time instead
of building them each time. It's set using ``use_registry_name`` and you'll have to be logged in to docker
using ``docker login``. If you can't use ``docker login`` (for example in PRs on Travis CI), you can set
``registry_pull_only`` and Arca will only attempt to pull from the registry and not push new images.

Settings:

* **python_version**: What Python version should be used.
  In theory any of
  `these versions <https://github.com/pyenv/pyenv/tree/master/plugins/python-build/share/python-build>`_ could be used,
  but only CPython 3.6 has been tested. The default is the Python version of the current environment.
  This setting is ignored if ``inherit_image`` is set.
* **keep_container_running**: When ``True``, containers aren't killed once the task finishes. Default is ``False``.
* **apt_dependencies**: For some python libraries, system dependencies are required,
  for example ``libxml2-dev`` and ``libxslt-dev`` are needed for ``lxml``.
  With this settings you can specify a list of system dependencies that will be installed via debian ``apt-get``.
  This setting is ignored if ``inherit_image`` is set since Arca can't
  determined how to install requirements on an unknown system.
* **disable_pull**: Disable pulling prebuilt Arca images from Docker Hub and build even the base images locally.
* **inherit_image**: If you don't wish to use the Arca images you can specify what image should be used instead.
  Pipenv must be available in the image if the repositories contain Pipenv files. Alternativelly Pipenv can be
  disabled by setting the option **pipfile_location** to ``None``.
* **use_registry_name**: Uses this registry to store images with installed requirements and dependencies to,
  tries to pull image from the registry before building it locally to save time.
* **registry_pull_only**: Disables pushing to registry.

(possible settings prefixes: ``ARCA_DOCKER_BACKEND_`` and ``ARCA_BACKEND_``)

.. _backends_vag:

Vagrant
-------

*arca.backend.VagrantBackend*

If you're extra paranoid you can use Vagrant to completely isolate the runtime in a Virtual Machine (VM).
This backend is actually a subclass of ``DockerBackend`` and uses docker in the VM to run the tasks.
Docker and Vagrant must be runnable by the current user.

The backend works by building the image with requirements and dependencies locally and pushing it to registry using ``use_to_registry_name``.
Then a VM is launched and the image is pulled there from the registry.
This takes some time when first launching the VM, but if the VM is reused often, the upload/download time is shorted.
The built images are also not lost when the VM is destroyed.

The backend inherits all the settings of ``DockerBackend`` (**keep_containers_running** is ``True`` by default) and has these extra settings:

* **box**: Vagrant box used in the VM. Either has to have docker version >= 1.8 or not have docker at all, in which case
  it will be installed when spinning up the VM.
  The default is `ailispaw/barge <https://app.vagrantup.com/ailispaw/boxes/barge>`_.
* **provider**: Vagrant provider, default is ``virtualbox``.
  Visit `vagrant docs <https://www.vagrantup.com/docs/providers/>`_ for more.
* **quiet**: Tells Vagrant and Fabric (which is used to run the task in the VM) to be quiet. Default is ``True``.
  Vagrant and Docker output is logged in separate files for each run in a folder ``logs`` in the :class:`Arca <arca.Arca>` ``base_dir``.
  The filename is logged in the arca logger (see bellow)
* **keep_vm_running**: Should the VM be kept up once a task finishes? By default ``False``.
  If set to ``True``, :meth:`stop_vm <arca.VagrantBackend.stop_vm>` can be used to stop the VM.
* **destroy**: When stopping the VM (either after a task or after :meth:`stop_vm` is called), should the VM be destroyed (= deleted) or just halted?
  ``False`` by default.

(possible settings prefixes: ``ARCA_VAGRANT_BACKEND_`` and ``ARCA_BACKEND_``)

Your own
--------

You can also create your own backend and pass it to :class:`Arca <arca.Arca>`. It has be a subclass of :class:`arca.BaseBackend` and
it has to implement its :meth:`run <arca.BaseBackend.run>` method.
