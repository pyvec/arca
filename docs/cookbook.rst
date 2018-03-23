.. _cookbook:

Cookbook
========

I need some files from the repositories
---------------------------------------

Besides running scripts from the repositories, there also might be some files in the repositories that you need,
e.g. images for a webpage. With the :class:`Arca <arca.Arca>` method :meth:`static_filename <arca.Arca.static_filename>`
you can get the absolute path to that file, to where Arca cloned it.
The method accepts a relative path (can be a :class:`pathlib.Path` or :class:`str`) to the file in the repository.

Example call (file ``images/example.png`` from the branch ``master`` of ``https://example.com/hello_word.git``):

.. code-block:: python

  arca = Arca()

  path_to_file = arca.static_filename("https://example.com/hello_word.git",
                                      "master",
                                      "images/example.png")

``path_to_file`` will be an absolute :class:`Path <pathlib.Path>`.

If the file is not in the repository, :class:`FileNotFoundError` will be raised. If the provided relative path
leads out of the repo, :class:`FileOutOfRangeError <arca.exceptions.FileOutOfRangeError>` will be raised.

I will be running a lot of tasks from the same repository
---------------------------------------------------------

Similarly as above, while you're building a webpage you might need to run a lot of tasks from the same repositories,
to render all the individual pages. However Arca has some overhead for each launched task, but these two
options can speed things up:

Singe pull
++++++++++

This option ensures that each branch is only cloned/pulled once per initialization of :class:`Arca <arca.Arca>`.
You can set it up with the :class:`Arca <arca.Arca>` ``single_pull`` option (``ARCA_SINGLE_PULL`` setting).
This doesn't help to speedup the first task from a repository, however each subsequent will run faster.
This setting is quite useful for keeping consistency, since the state of the repository can't change in the middle
of running multiple tasks.

You can tell :class:`Arca <arca.Arca>` to pull again (if a task from that repo/branch is called again)
by calling the method :meth:`Arca.pull_again <arca.Arca.pull_again>`:

.. code-block:: python

  arca = Arca()

  ...

  # only this specific branch will be pulled again
  arca.pull_again(repo="https://example.com/hello_word.git", branch="master")

  # all branches from this repo will be pulled again
  arca.pull_again(repo="https://example.com/hello_word.git")

  # everything will be pulled again
  arca.pull_again()


Running container
+++++++++++++++++

If you're using the :ref:`Docker <backends_doc>` backend, you can speed up things by keeping the containers
for running the tasks running. Since a container for each repository is launched, this can speed up things considerably,
because starting up, copyting files and shutting down containers takes time.

This can be enabled by setting the ``keep_container_running`` option to ``True``.
When you're done with running the tasks you can kill the containers by calling the method
:meth:`DockerBackend.stop_containers <arca.DockerBackend.stop_containers>`:

.. code-block:: python

  arca = Arca(backend=DockerBackend())

  ...

  arca.backend.stop_containers()
