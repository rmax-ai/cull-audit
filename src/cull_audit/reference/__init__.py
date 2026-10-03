"""Optional provider reference adapters for cull-audit.

The public image-pass helpers are re-exported here for small integrations;
the CLI imports their implementation modules directly.
"""

from .passes import ReferenceRunner, run_reference

__all__ = ["ReferenceRunner", "run_reference"]
