from __future__ import annotations

import contextvars

# Phase 4.5: correlation ID propagation without threading a new parameter through every one of the
# ~50 existing self.audit.record(...)/self.exceptions.create(...) call sites across Finance,
# Procurement, and Post-Order. The API layer's CorrelationMiddleware sets this once per request; every
# audit/exception write made anywhere during that request automatically picks it up.
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("sanocea_correlation_id", default=None)


def set_correlation_id(value: str | None) -> contextvars.Token:
    return _correlation_id_var.set(value)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()
