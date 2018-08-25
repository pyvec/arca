Installation
============

Requirements
------------

.. remember to update README when updating this

* Python >= 3.6

Requirements for certain backends:

* `Pipenv <https://docs.pipenv.org/>`_ (for certain usecases in :ref:`Virtualenv Backend <backends_venv>`)
* `Docker <https://www.docker.com/>`_ (for :ref:`Docker Backend <backends_doc>` and :ref:`Vagrant Backend <backends_vag>`)
* `Vagrant <https://www.vagrantup.com/>`_ (for the :ref:`Vagrant Backend <backends_vag>`)

Installation
------------

.. remember to update README when updating this

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
