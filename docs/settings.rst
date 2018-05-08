Settings
========

.. _configuring:

Configuring Arca
----------------

There are multiple ways to configure :class:`Arca <arca.Arca>` and its backends. (The used options are described :ref:`bellow <options>`.)

1. You can initialize the class and backends directly and set it's options via constructor arguments.

.. code-block:: python

  from arca import Arca, VenvBackend

  arca = Arca(
    base_dir=".custom_arca_dir",
    backend=VenvBackend(cwd="utils")
  )

This option is the most direct but it has one caveat - options set by this method cannot be overridden by the following methods.

2. You can pass a dict with settings. The keys have to be uppercase and prefixed with ``ARCA_``.
Keys for backends can be set in two ways. The first is generic ``ARCA_BACKEND_<key>``,
the second has a bigger priority ``ARCA_<backend_name>_BACKEND_<key>``.
For example the same setting as above would be written as:

.. code-block:: python

  arca = Arca(settings={
    "ARCA_BASE_DIR": ".custom_arca_dir",
    "ARCA_BACKEND": "arca.VenvBackend",
    "ARCA_VENV_BACKEND_CWD": "utils",
    "ARCA_BACKEND_CWD": "",  # this one is ignored since it has lower priority
  })

3. You can configure :class:`Arca <arca.Arca>` with environ variables, with keys being the same as in the second method.
Environ variables override settings from the second method.

You can combine these methods as long as you remember that options explicitly specified in constructors
cannot be overridden by the settings and environ methods.

.. _options:

Basic options
-------------

This section only describes basic settings, visit the :ref:`cookbook <cookbook>` for more.

Arca class
++++++++++

**base_dir** (`ARCA_BASE_DIR`)

Arca needs to clone repositories and for certain backends also store some other files. This options determines
where the files should be stored. The default is ``.arca``. If the folder doesn't exist it's created.

**backend** (`ARCA_BACKEND`)

This options tells how the tasks should be launched. This setting can be provided as a string, a class or a instance.
The default is ``arca.CurrentEnvironmentBackend``, the :ref:`Current Environment Backend <backends_cur>`.

Backends
++++++++

This section describes settings that are common for all the backends.

**requirements_location** (`ARCA_BACKEND_REQUIREMENTS_LOCATION`)

Tells backends where to look for a requirements file in the repositories, so it must be a relative path. You can set it
to ``None`` to indicate there are no requirements. The default is ``requirements.txt``.

**requirements_timeout** (`ARCA_BACKEND_REQUIREMENTS_TIMEOUT`)

Tells backends how long the installing of requirements can take, in seconds.
The default is 120 seconds.
If the limit is exceeded :class:`BuildTimeoutError <arca.exceptions.BuildTimeoutError>` is raised.

**cwd** (`ARCA_BACKEND_CWD`)

Tells Arca in what working directory the tasks should be launched, so again a relative path.
The default is the root of the repository.
