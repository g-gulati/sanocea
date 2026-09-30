"""Read-only bridge from the Command Centre API to the SEO monitoring worker (packages/seo-stack)."""
from .client import SeoBridge, SeoWorkerUnreachable, VIEWS, require_internal_operator

__all__ = ["SeoBridge", "SeoWorkerUnreachable", "VIEWS", "require_internal_operator"]
