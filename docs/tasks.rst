Tasks
=====

:class:`arca.Task` instances are used to define what should be run in the repositories. The definition
consists of a string representation of a callable and arguments.

EntryPoints (from the `entrypoints <http://entrypoints.readthedocs.io/en/latest/>`_ library) are used for
defining the callables. Any callable can be used if the result is json-serializable by the standard library :mod:`json`.

Let's say we have file ``package/test.py`` in the repository:

.. code-block:: python

  def func():
    x = Test()
    return x.run()

  class Test:
    def run(self):
      ...
      return "Hello!"

    @staticmethod
    def method():
      x = Test()
      return x.run()

In that case, the following two tasks would have the same result:

.. code-block:: python

  task1 = Task("package.test:func")
  task2 = Task("package.test:Test.method")

Arguments
---------

Both positional and keyword arguments can be provided to the task,
however they need to be json-serializable (so types ``dict``, ``list``, ``str``, ``int``, ``float``, ``bool`` or ``None``).

Let's say we the following file ``test.py`` in the repository:

.. code-block:: python

  def func(x, *, y=5):
    return x * y

The following tasks would use the fuction (with the default ``y``):

.. code-block:: python

  task1 = Task("test:func", args=[5])  # -> result would be 25
  task2 = Task("test:func", kwargs={"x": 5})  # -> result would be 25 again

Since the ``x`` parameter is positional, both ways can be used. However, if we wanted to set ``y``, the task would be
set up like this:

.. code-block:: python

  task1 = Task("test:func", args=[5], kwargs={"y": 10})  # -> 50
  task2 = Task("test:func", kwargs={"x": 5, "y": 10})  # -> 50 again

Timeout
-------

The :class:`arca.Task` class allows for a timeout to be defined with the task with the keyword argument ``timeout``.
It must be a positive integer.
The default value is 5 seconds.

When a task exceeds a timeout, :class:`arca.exceptions.BuildTimeoutError` is raised.

.. _result:

Result
------

The output of a task is stored and returned in a :class:`arca.Result` instance.
Anything that's json-serializable can be returned from the entrypoints.
The :class:`arca.Result` instances contain three attributes.
``output`` contains the value returned from the entrypoint.
``stdout`` and ``stderr`` contain things written to the standard outputs.

Arca uses :func:`contextlib.redirect_stdout` and :func:`contextlib.redirect_stderrr` to catch the standard outputs,
which only redirect things written from standard Python code -- for example output from a subprocess is not caught.
Due to the way backends launch tasks the callables cannot output anything that is not redirectable by these two context managers.
