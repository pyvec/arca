Changes
=======

0.3.0 (2018-08-25)
******************

Changes
  * Removed CurrentEnvironmentBackend's capability to process requirements - all requirements are ignored. (**BACKWARDS INCOMPATIBLE**)
  * Added support for installing requirements using `Pipenv <https://docs.pipenv.org/>`_.
    The directory containing ``Pipfile`` and ``Pipfile.lock`` is set by the backend option **pipfile_location**, by default the root of the repository is selected.
    The Pipenv files take precedence over regular requirement files.
  * The ``Result`` class now has two more attributes, ``stdout`` and ``stderr`` with the outputs of launched tasks to standard output and error.
    Priting is therefore now allowed in the endpoints.
  * Using UTF-8 locale in Docker images used in ``DockerBackend``.
  * Supporting Python 3.7.

0.2.1 (2018-06-11)
******************

Updated dogpile.cache to 0.6.5, enabling compatability with Python 3.7.
Updated the Docker backend to be able to run on Python betas.

0.2.0 (2018-05-09)
******************

This release has multiple backwards incompatible changes against the previous release.

Changes:
  * Using extras to install Docker and Vagrant dependencies

    * ``pip install arca[docker]`` or ``pip install arca[vagrant]`` has to be used

  * Automatically using cloned repositories as reference for newly cloned branches
  * Using Debian as the default base image in the Docker backend:

    * **apk_dependencies** changed to **apt_dependencies**, now installing using `apt-get`

  * Vagrant backend only creates one VM, instead of multiple -- see its documentation
  * Added timeout to tasks, 5 seconds by default. Can be set using the argument **timeout** for ``Task``.
  * Added timeout to installing requirements, 300 seconds by default. Can be set using the **requirements_timeout** configuration option for backends.

0.1.1 (2018-04-23)
******************

Updated gitpython to 2.1.9

0.1.0 (2018-04-18)
******************

Initial release

Changes:
 * Updated PyPI description and metadata

0.1.0a0 (2018-04-13)
********************

Initial alfa release
