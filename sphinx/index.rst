.. include:: ../README.rst

.. include:: ../DOCUMENTATION.rst

.. include:: ../CONTRIBUTING.rst

.. _api-ref:

API Reference
=============

Even though jsonargparse has several internal modules, users are expected to
only import from ``jsonargparse`` or ``jsonargparse.typing``. This allows
internal refactoring without affecting dependants. Only the objects in
``jsonargparse.__all__`` and ``jsonargparse.typing.__all__`` are public, and
these are the ones included in this API reference.


jsonargparse
------------
.. automodule:: jsonargparse

.. autodata:: jsonargparse.Unset

jsonargparse.typing
-------------------
.. automodule:: jsonargparse.typing
    :exclude-members: get_import_path, import_object


Index
=====

* :ref:`migrate-v5`
* :ref:`talks-and-articles`
* :ref:`changelog`
* :ref:`license`
* :ref:`genindex`
