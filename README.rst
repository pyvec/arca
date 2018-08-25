Arca
====

.. image:: https://img.shields.io/travis/mikicz/arca.svg
   :target: https://travis-ci.org/mikicz/arca

.. image:: https://img.shields.io/codecov/c/github/mikicz/arca.svg
   :target: https://codecov.io/gh/mikicz/arca

.. image:: https://img.shields.io/pypi/v/arca.svg
   :target: https://pypi.org/project/arca/

.. image:: https://img.shields.io/github/license/mikicz/arca.svg?style=flat
   :target: https://github.com/mikicz/arca/blob/master/LICENSE

.. image:: https://img.shields.io/readthedocs/arca.svg
   :target: https://arca.readthedocs.io/

Arca is a library for running Python functions (callables) from git repositories in various states of isolation.
Arca can also cache the results of these callables using `dogpile.cache <https://dogpilecache.readthedocs.io/en/latest/>`_.

Getting started
***************

Glossary
++++++++

* **Arca** - name of the library. When written as ``Arca``, the main interface class is being referenced.
* **Task** - definition of the function (callable), consists of a reference to the object and arguments.
* **Backend** - a way of running tasks.

Installation
++++++++++++

Requirements
------------

* Python >= 3.6

Requirements for certain backends:

* `Pipenv <https://docs.pipenv.org/>`_ (for certain usecases in `Virtualenv Backend <https://arca.readthedocs.io/en/latest/backends.html#virtual-environment>`_)
* `Docker <https://www.docker.com/>`_ (for `Docker Backend <https://arca.readthedocs.io/en/latest/backends.html#docker>`_
  and `Vagrant Backend <https://arca.readthedocs.io/en/latest/backends.html#vagrant>`_)
* `Vagrant <https://www.vagrantup.com/>`_ (for the `Vagrant Backend <https://arca.readthedocs.io/en/latest/backends.html#vagrant>`_)

Installation
------------

To install the last stable version:

.. code-block:: bash

  python -m pip install arca

If you want to use the Docker backend:

.. code-block:: bash

  python -m  pip install arca[docker]

Or if you want to use the Vagrant backend:

.. code-block:: bash

  python -m pip install arca[vagrant]

Or if you wish to install the upstream version:

.. code-block:: bash

  python -m pip install git+https://github.com/mikicz/arca.git#egg=arca
  python -m pip install git+https://github.com/mikicz/arca.git#egg=arca[docker]
  python -m pip install git+https://github.com/mikicz/arca.git#egg=arca[vagrant]

Example
+++++++

To run a Hello World example you'll only need the ``arca.Arca`` and ``arca.Task`` classes.
``Task`` is used for defining the task that's supposed to be run in the repositories.
``Arca`` takes care of all the settings and provides the basic API for running the tasks.

Let's say we have the following file, called ``hello_world.py``,
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
``result`` would be a ``arca.Result`` instance. ``arca.Result`` has three attributes,
``output`` with the return value of the function call, ``stdout`` and ``stderr`` contain things printed to the standard outputs
(see the section about `Result <http://arca.readthedocs.io/en/latest/tasks.html#result>`_ for more info about the capture of the standard outputs).
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

Contributions are welcomed! Feel free to open a issue or submit a pull request on `GitHub <https://github.com/mikicz/arca>`_!

.. split_here

Links
*****

- Repository: `GitHub <https://github.com/mikicz/arca>`_
- PyPi package: `arca <https://pypi.python.org/pypi/arca>`_
- CI: `Travis <https://travis-ci.org/mikicz/arca>`_
- Test coverage: `Codecov <https://codecov.io/gh/mikicz/arca>`_
- Documentation: `Read The Docs <https://arca.readthedocs.io/>`_

License
*******

This project is licensed under the MIT License - see the `LICENSE <https://github.com/mikicz/arca/blob/master/LICENSE>`_ file for details.
