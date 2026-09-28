"""Regenerate the checked-in JSON Schemas from the packet models."""
from . import write_schemas

for path in write_schemas():
    print(path)
