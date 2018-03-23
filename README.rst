Arca
====

.. image:: https://img.shields.io/travis/mikicz/arca.svg
   :target: https://travis-ci.org/mikicz/arca

.. image:: https://img.shields.io/codecov/c/github/mikicz/arca.svg
   :target: https://codecov.io/gh/mikicz/arca

.. image:: https://img.shields.io/pypi/v/arca.svg
   :target: https://pypi.python.org/pypi/arca

.. image:: https://img.shields.io/github/license/mikicz/arca.svg?style=flat
   :target: https://github.com/mikicz/arca/blob/master/LICENSE

.. image:: https://img.shields.io/readthedocs/arca.svg
   :target: https://arca.readthedocs.io/

Arca is a library for running Python scripts from git repositories in various states of isolation.
Arca can also cache the results of these scripts using `dogpile.cache <https://dogpilecache.readthedocs.io/en/latest/>`_.

Getting started
***************

Glossary
++++++++

* **Arca** - name of the library. When written as ``Arca``, the main interface class is being referenced.
* **Task** - definition of the script, consists of a reference to a callable object and arguments.
* **Backend** - a way of running tasks.

Installation
++++++++++++

Requirements
------------

* Python >= 3.6

Requirements for certain backends:

* `Docker <https://www.docker.com/>`_ (for `Docker Backend <https://arca.readthedocs.io/en/latest/backends.html#docker>`_
  and `Vagrant Backend <https://arca.readthedocs.io/en/latest/backends.html#vagrant>`_)
* `Vagrant <https://www.vagrantup.com/>`_ (for the `Vagrant Backend <https://arca.readthedocs.io/en/latest/backends.html#vagrant>`_)

Installation
------------

To install the last stable version:

.. code-block:: bash

  python -m pip install arca

Or if you wish to install the upstream version:

.. code-block:: bash

  python -m pip install git+https://github.com/mikicz/arca.git#egg=arca

Example
+++++++

To run a Hello World example you'll only need the ``arca.Arca`` and ``arca.Task`` classes.
``Task`` is used for defining the task that's supposed to be run in the repositories.
``Arca`` takes care of all the settings and provides the basic API for running the tasks.

Let's day we have the following file, called ``hello_world.py``,
in a repository ``https://example.com/hello_word.git``, on branch ``master``.

.. code-block:: python

  def say_hello():
     return "Hello World!"

To call the function using Arca, the following example would do so:

.. code-block:: python

  from arca import Arca, Task

  task = Task("hello_world:say_hello")
  arca = Arca()

  result = arca.run("https://example.com/hello_word.git", "master", task)
  print(result.output)

The code would print ``Hello World!``.
``result`` would be a ``arca.Result`` instance which currently only has one attribute,
``output``, with the output of the function call.
If the task fails, ``arca.exceptions.BuildError`` would be raised.

By default, the `Current Environment Backend <https://arca.readthedocs.io/en/latest/backends.html#current-environment>`_ is used to run tasks,
which uses the current Python, launching the code in a subprocess. You can learn about backends `here <https://arca.readthedocs.io/en/latest/backends.html>`_.

Further reading
***************

You can read the full documentation on `Read The Docs <https://arca.readthedocs.io/>`_.

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
- Documentation: `Read The Docs <https://arca.readthedocs.io/>`_

License
*******

This project is licensed under the MIT License - see the `LICENSE <LICENSE>`_ file for details.
