# ADR 0001: Python importable package layout

Phase 0 uses Python because the existing workspace is Python/FastAPI based and
pytest/FastAPI are already available locally.

The approved architecture listed package names such as `domain-contract`.
Python cannot import modules with hyphens, so implementation directories use
underscores (`domain_contract`, `policy_engine`, `connector_sdk`). The logical
responsibilities remain the same.

