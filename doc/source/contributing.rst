============
Contributing
============
.. include:: ../../CONTRIBUTING.rst


Python API
----------

No internal API stability guarantees are made, but for reference
here is a basic outline of the source implementation:

.. automodule:: bindep
   :members:

.. automodule:: bindep.depends
   :members:

.. automodule:: bindep.main
   :members:


Internal Unit Tests
-------------------

The bindep utility is developed following a test-driven methodology.
These are the current tests run to ensure its internal consistency
for every commit:

.. automodule:: bindep.tests
   :members:

.. automodule:: bindep.tests.test_depends
   :members:

.. automodule:: bindep.tests.test_main
   :members:
