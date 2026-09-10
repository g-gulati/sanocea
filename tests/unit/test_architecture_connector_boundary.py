from __future__ import annotations

import ast
from pathlib import Path

"""Architecture guard: prevents regression of the platform-name leak the WooCommerce
platform-independence test found (packages/post_order/operations.py,
packages/product_onboarding/publication.py, and the now-removed packages/order_ops/monitoring.py -
superseded by PostOrderOperationsService, see closure item 2 of multi-platform connector hardening -
all hardcoded the literal string "shopify" instead of deriving channel identity from the resolved
connector's own `.name`).

AST-based rather than a grep, per instruction - a grep would false-positive on the word "shopify"
appearing inside a comment or a docstring explaining WHY something is now platform-agnostic (this file
included), and would false-negative on multi-line or dynamically-built import statements. Parsing the
real AST and only inspecting import statements and non-docstring string-constant nodes is exact.

Two independent checks:
1. No PROTECTED_PATHS file may `import` (or `from ... import`) anything under `sanocea.connectors.*`,
   except the explicit, narrow composition-root allowlist (ALLOWED_CONNECTOR_IMPORT_FILES) - connector
   selection is infrastructure/runtime composition, never Commerce-domain code's concern.
2. No PROTECTED_PATHS file may contain a string literal that is EXACTLY (after strip+lower) one of
   FORBIDDEN_LITERALS ("shopify", "woocommerce", ...) - domain code must derive channel identity from
   `connector.name`, never hardcode a platform's name. Module/class/function DOCSTRINGS are excluded
   (this guard is about VALUES used in logic, not prose explaining the guard itself); plain `#`
   comments are already invisible to ast.parse and need no special handling.
"""

ROOT = Path(__file__).resolve().parents[2]

PROTECTED_PATHS = [
    "packages/post_order",
    "packages/finance",
    "packages/procurement",
    "packages/product_onboarding",
    "packages/support",
    "packages/policy_engine",
    "packages/domain_contract",
    "packages/runtime/commands.py",
    "packages/runtime/queries.py",
    "apps/api/app.py",
    "workers/workflow/order_orchestrator.py",
    "workers/workflow/support_orchestrator.py",
    "workers/reconciliation_worker.py",
]

# The ONLY files allowed to import a specific connector implementation - the infrastructure/runtime
# composition root. Adding a new platform means adding a factory here, never touching PROTECTED_PATHS.
ALLOWED_CONNECTOR_IMPORT_FILES = {
    "packages/runtime/service_graph.py",
    "packages/runtime/storefront_registry.py",  # imports Channel only today, but kept in the allowlist
}

FORBIDDEN_LITERALS = {"shopify", "woocommerce", "shopify_live"}


def _iter_protected_files() -> list[Path]:
    files: list[Path] = []
    for rel in PROTECTED_PATHS:
        target = ROOT / rel
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.py")))
    return [f for f in files if "__pycache__" not in f.parts]


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Identifies the ast.Constant nodes that are genuine module/class/function docstrings (the first
    statement of their body, a bare string expression) - not the same thing as "any string that looks
    like prose"; a docstring here is specifically the AST shape Python itself recognizes as one."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def test_commerce_domain_does_not_import_connector_implementations_directly():
    violations: list[str] = []
    for path in _iter_protected_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_CONNECTOR_IMPORT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("sanocea.connectors.") or alias.name.startswith("connectors."):
                        violations.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("sanocea.connectors.") or module.startswith("connectors."):
                    violations.append(f"{rel}:{node.lineno}: from {module} import ...")
    assert not violations, (
        "Commerce-domain code must not import a specific connector implementation directly - "
        "connector selection belongs in packages/runtime/service_graph.py / storefront_registry.py "
        "(infrastructure/runtime composition), never in domain code:\n" + "\n".join(violations)
    )


def test_commerce_domain_does_not_hardcode_storefront_platform_literals():
    violations: list[str] = []
    for path in _iter_protected_files():
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        skip_ids = _docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in skip_ids:
                    continue
                if node.value.strip().lower() in FORBIDDEN_LITERALS:
                    violations.append(f"{rel}:{node.lineno}: literal {node.value!r}")
    assert not violations, (
        "Commerce-domain code must never hardcode a storefront platform name as a string value - "
        "derive it from the resolved connector's own `.name` (self.storefront(merchant_id).name) "
        "instead. This is exactly the bug the WooCommerce platform-independence test found and fixed "
        "(hardcoded 'shopify' literals in post_order/operations.py, product_onboarding/publication.py, "
        "order_ops/monitoring.py):\n" + "\n".join(violations)
    )
