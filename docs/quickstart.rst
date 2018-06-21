Quickstart
==========

Glossary
--------

.. remember to update README when updating this

* **Arca** - name of the library. When written as :class:`Arca <arca.Arca>`, the main interface class is being referenced.
* **Task** - definition of the function (callable), consists of a reference to the object and arguments.
* **Backend** - a way of running tasks.

Example
-------

.. remember to update README when updating this

To run a Hello World example you'll only need the :class:`arca.Arca` and :class:`arca.Task` classes.
:class:`Task <arca.Task>` is used for defining the task that's supposed to be run in the repositories.
:class:`Arca <arca.Arca>` takes care of all the settings and provides the basic API for running the tasks.

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

``result`` would be a :class:`Result <arca.Result>` instance. :class:`Result <arca.Result>` has three attributes,
``output`` with the return value of the function call, ``stdout`` and ``stderr`` contain things printed to the standard outputs
(see the section about :ref:`Result <result>` for more info about the capture of the standard outputs).
If the task fails, :class:`arca.exceptions.BuildError` would be raised.

By default, the :ref:`Current Environment Backend <backends_cur>` is used to run tasks,
which uses the current Python, launching the code in a subprocess. You can learn about backends :ref:`here <backends>`.
