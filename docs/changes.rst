Changes
=======

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
