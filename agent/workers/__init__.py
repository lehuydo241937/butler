"""
agent/workers/ — Script Inventory for Kuro OS
Each .py file here is a self-contained script that Kuro can discover and run.

Conventions:
  - Every script must have a module-level docstring (first line = description).
  - If the script is callable, expose a `run(**kwargs)` function.
  - Type-annotate all `run()` parameters so /sync-inventory can build the schema.
"""
