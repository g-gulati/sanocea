"""Connector worker package.

Phase 0 invokes connectors directly in tests/API. Production should run this as
an async worker consuming webhook and command jobs.
"""

