.. _caching:

Caching
=======

Arca can cache results of the tasks using `dogpile.cache <https://dogpilecache.readthedocs.io/en/latest/>`_.
The default cache backend is ``dogpile.cache.null``, so no caching.

You can setup caching with the backend setting ``ARCA_CACHE_BACKEND`` and all the arguments needed for setup can be set
using ``ARCA_CACHE_BACKEND_ARGUMENTS`` which can either be a dict or a json string.

Example setup:

.. code-block:: python

    arca = Arca(settings={
        "ARCA_CACHE_BACKEND": "dogpile.cache.redis",
        "ARCA_CACHE_BACKEND_ARGUMENTS": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
    })

To see all available cache backends and their settings,
please visit the ``dogpile.cache`` `documentation <https://dogpilecache.readthedocs.io/en/latest/>`_.
Some of the other backends might have other python dependencies.

When :class:`Arca <arca.Arca>` is being initialized, a check is made if the cache backend is writable and readable,
which raises an :class:`arca.exceptions.ArcaMisconfigured` if it's not.
If the cache requires some python dependency :class:`ModuleNotFoundError` will be raised.
If you wish to ignore these errors, ``ignore_cache_errors`` setting can be used.
