"""Boolean-only policy loader (YAML-only, strict).

This loader returns a mapping of:
    rule_id -> enabled (bool)

Constraints/assumptions:
- **Only YAML** is supported.
- The document **must** contain a top-level `rules:` mapping.
- Values under `rules:` **must be booleans**; any other type raises.
- Missing known rules default to **True** (enabled).
- Unknown keys are ignored.
- If `path` is None, all known rules are enabled.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict

from yaml import safe_load

from .rules import registry


class PolicyWarning(UserWarning):
    pass


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


essential_rules = tuple(registry.list_rule_ids())


def _normalize_mapping(data: Dict[str, Any]) -> Dict[str, bool]:
    """Extract a strict rule_id -> bool map from a parsed YAML document.

    - Requires a top-level `rules:` mapping.
    - Every value in `rules:` must be a bool.
    - Missing rule IDs default to True and emit a warning.
    - Unknown keys under `rules:` are ignored and emit a warning.
    """
    if (
        not isinstance(data, dict)
        or "rules" not in data
        or not isinstance(data["rules"], dict)
    ):
        raise ValueError("Policy file must contain a top-level 'rules' mapping.")

    raw = data["rules"]
    enabled_map: Dict[str, bool] = {}

    # Warn on unknown keys
    unknown = [k for k in raw.keys() if k not in essential_rules]
    for k in sorted(unknown):
        warnings.warn(
            f"Ignoring unknown policy rule id: '{k}'",
            PolicyWarning,
            stacklevel=2,
        )

    # Fill known rules; warn when defaulting to True
    for rid in essential_rules:
        if rid in raw:
            val = raw[rid]
            if not isinstance(val, bool):
                raise TypeError(
                    f"Policy value for '{rid}' must be a boolean, got {type(val).__name__}."
                )
            enabled_map[rid] = val
        else:
            enabled_map[rid] = True  # default ON
            warnings.warn(
                f"Policy does not specify rule '{rid}'; defaulting to True (enabled)",
                PolicyWarning,
                stacklevel=2,
            )

    return enabled_map


def load_enabled_map(path: str | None) -> Dict[str, bool]:
    """Load a boolean policy map from YAML at `path`.

    If `path` is None, returns all rules enabled.
    """
    if path is None:
        return {rid: True for rid in essential_rules}

    text = _read_file(path)
    parsed = safe_load(text) or {}
    return _normalize_mapping(parsed)
