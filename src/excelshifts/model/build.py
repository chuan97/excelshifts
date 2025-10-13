"""Model assembly for excelshifts.

Build a CP-SAT model by:
  1) creating decision variables X[i,j,k] for a given immutable `state.Instance`, and
  2) applying a list of class-based rule instances (loaded from YAML via io.policy).

No objective is defined here; callers may set one (e.g., maximize coverage).
"""

from typing import Any, Dict, Tuple

from ortools.sat.python import cp_model

import excelshifts.state as state
from excelshifts.io.policy import load_rules
from excelshifts.model.constraints import apply_rules
from excelshifts.model.variables import create_shifts

essential_return = Tuple[
    cp_model.CpModel, Dict[tuple[int, int, int], Any], Dict[str, Any]
]


def build_model(
    *,
    instance: state.Instance,
    policy_path: str,
) -> essential_return:
    """Build the CP-SAT model and apply rule builders.

    Parameters
    ----------
    instance : state.Instance
        Immutable problem data (residents, days, positions, etc.).
    policy_path : str
        Path to YAML policy file defining rules.

    Returns
    -------
    model : cp_model.CpModel
        The constructed CP-SAT model.
    shifts : Dict[(i,j,k), BoolVar]
        Decision variables mapping (resident, day, shift_type_index) -> BoolVar.
    enables : Dict[str, Any]
        Mapping rule_id -> enable literal (0/1 var) returned by its builder.
    """
    model = cp_model.CpModel()
    shifts = create_shifts(model, instance)
    rules = load_rules(policy_path)
    enables = apply_rules(
        model=model,
        instance=instance,
        shifts=shifts,
        rules=rules,
    )

    return model, shifts, enables
