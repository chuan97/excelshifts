"""Minimal YAML policy loader that instantiates rule classes.

Assumptions (strict):
- The file is YAML and contains a top-level key `rules`.
- `rules` is a list of **mappings**. Each item MUST have:
    - `id`: the rule class ID (string)
    - optional `init`: a mapping of constructor kwargs forwarded as-is
- No normalization, no coercion, no warnings. If the shape is wrong, we raise.
"""

from __future__ import annotations

import warnings
from typing import List

from yaml import safe_load

from excelshifts.model.constraints import BaseRule, get_rule_class


class PolicyWarning(UserWarning):
    pass


def load_rules(path: str) -> List[BaseRule]:
    with open(path, "r", encoding="utf-8") as stream:
        parsed = safe_load(stream)

    if not isinstance(parsed, dict) or "rules" not in parsed:
        raise ValueError("Policy file must contain a top-level 'rules' list.")
    rules_list = parsed["rules"]
    if not isinstance(rules_list, list):
        raise ValueError(
            "'rules' must be a list of mappings with keys 'id' and optional 'init'."
        )

    instances: List[BaseRule] = []
    for idx, item in enumerate(rules_list):
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(
                f"rules[{idx}] must be a mapping with at least the key 'id'."
            )
        rid = item["id"]
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError(f"rules[{idx}].id must be a non-empty string.")
        try:
            cls = get_rule_class(rid.strip())
        except KeyError:
            warnings.warn(
                f"Unknown rule id '{rid.strip()}', skipping.",
                PolicyWarning,
                stacklevel=2,
            )
            continue

        init = item.get("init", {})
        if init is None:
            init = {}
        if not isinstance(init, dict):
            raise ValueError(f"rules[{idx}].init must be a mapping if provided.")

        rule = cls(**init)
        if not isinstance(rule, BaseRule):
            raise TypeError(f"Constructed object is not a BaseRule: {rule!r}")
        instances.append(rule)

    return instances
