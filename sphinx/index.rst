.. include:: ../README.rst

.. include:: ../DOCUMENTATION.rst

.. include:: ../CONTRIBUTING.rst

.. _api-ref:

API Reference
=============

Even though jsonargparse has several internal modules, users are expected to
only import from ``jsonargparse`` or ``jsonargparse.typing``. This allows doing
internal refactoring without affecting dependants. Only objects explicitly
exposed in ``jsonargparse.__init__.__all__`` and in
``jsonargparse.typing.__all__`` are included in this API reference and is what
can be considered public.


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
* :ref:`changelog`
* :ref:`license`
* :ref:`genindex`
