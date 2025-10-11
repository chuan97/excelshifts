"""Model assembly for excelshifts (Option B).

Build a CP-SAT model by:
  1) creating decision variables X[i,j,k] for a given immutable `state.Instance`, and
  2) applying all (or selected) rule builders according to a boolean policy map.

No objective is defined here; callers may set one (e.g., maximize coverage).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from ortools.sat.python import cp_model

import excelshifts.state as state

from ..rules.base import RuleSpec
from ..rules.registry import BUILDERS, RULES
from .variables import create_shifts

essential_return = Tuple[
    cp_model.CpModel, state.Instance, Dict[tuple[int, int, int], Any], Dict[str, Any]
]


def build_model(
    *,
    instance: state.Instance,
    enabled_map: Dict[str, bool] | None = None,
    rule_ids: Iterable[str] | None = None,
) -> essential_return:
    """Build the CP-SAT model and apply rule builders.

    Parameters
    ----------
    instance : state.Instance
        Immutable problem data (residents, days, positions, etc.).
    enabled_map : Dict[str, bool] | None
        Simple `rule_id -> bool` dictionary (missing keys default to True).
    rule_ids : Iterable[str] | None
        If provided, build only these rules (in the given order). If None,
        build all registered rules in canonical order.

    Returns
    -------
    model : cp_model.CpModel
        The constructed CP-SAT model.
    instance : state.Instance
        Echo of the input instance for convenience.
    shifts : Dict[(i,j,k), BoolVar]
        Decision variables mapping (resident, day, shift_type_index) -> BoolVar.
    enables : Dict[str, Any]
        Mapping rule_id -> enable literal (0/1 var) returned by its builder.
    """
    model = cp_model.CpModel()

    # Decision variables for this instance
    shifts = create_shifts(model, instance)

    # Apply rule builders
    enables = apply_rules(
        model=model,
        instance=instance,
        shifts=shifts,
        rule_ids=rule_ids,
        enabled_map=enabled_map,
    )

    return model, instance, shifts, enables


def apply_rules(
    model: Any,
    instance: Any,
    shifts: Any,
    rule_ids: Iterable[str] | None = None,
    enabled_map: Dict[str, bool] | None = None,
) -> Dict[str, Any]:
    """Build rules on the given model.

    Parameters
    ----------
    model : CpModel-like
        The OR-Tools CP-SAT model.
    instance : Any
        Object with the problem instance data expected by builders.
    shifts : Any
        Object/dict with the problem shifts data expected by builders.
    rule_ids : Iterable[str] | None
        If provided, build only these rule IDs (in the given order). Missing IDs are ignored.
        If None, build **all** rules in the canonical BUILDERS order.
    enabled_map : Dict[str, bool] | None
        Optional: boolean switches per rule_id. Missing keys default to True.

    Returns
    -------
    Dict[str, Any]
        Mapping rule_id -> enable literal (0/1 var) returned by its builder.

        For rules disabled in the policy, we add `enable == 0`. For enabled rules, we intentionally do not add `enable == 1`; callers may pass these literals as assumptions to obtain UNSAT cores.
    """
    specs = make_specs_from_booleans(enabled_map)
    enables: Dict[str, Any] = {}

    if rule_ids is None:
        # Default: build in canonical order defined by BUILDERS
        for fn in BUILDERS:
            rid = fn.__name__
            spec = specs[rid]
            enable = fn(model, instance, shifts, spec)
            if not spec.enabled:
                model.Add(enable == 0)
            enables[rid] = enable
    else:
        for rid in rule_ids:
            builder = RULES.get(rid)
            if builder is None:
                continue
            spec = specs[rid]
            enable = builder(model, instance, shifts, spec)
            if not spec.enabled:
                model.Add(enable == 0)
            enables[rid] = enable

    return enables


def make_specs_from_booleans(
    enabled_map: Dict[str, bool] | None = None,
) -> Dict[str, RuleSpec]:
    """Create RuleSpec objects from a simple boolean map.

    Any missing rule defaults to enabled=True.
    """
    specs: Dict[str, RuleSpec] = {}
    for rule_id in RULES.keys():
        enabled = True if enabled_map is None else bool(enabled_map.get(rule_id, True))
        specs[rule_id] = RuleSpec(id=rule_id, enabled=enabled)
    return specs
