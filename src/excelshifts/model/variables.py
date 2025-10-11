"""
Decision variable construction for excelshifts (Option B layout).

This module exposes a single helper to create the CP-SAT decision variables
for a given immutable `state.Instance`.
"""

from __future__ import annotations

from typing import Any, Dict

from ortools.sat.python import cp_model

import excelshifts.state as state


def create_shifts(
    model: cp_model.CpModel, instance: state.Instance
) -> Dict[tuple[int, int, int], Any]:
    """
    Create the decision variables X[i,j,k] ∈ {0,1} indicating whether
    resident i is assigned to shift type k on day j.

    Parameters
    ----------
    model : cp_model.CpModel
        The CP-SAT model to which variables are attached.
    instance : state.Instance
        Immutable problem data (residents, days, etc.).

    Returns
    -------
    Dict[(int,int,int), BoolVar-like]
        Mapping (i, j, k) -> BoolVar.
    """
    shifts: Dict[tuple[int, int, int], Any] = {}
    for i, _ in enumerate(instance.residents):
        for j, _ in enumerate(instance.days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")
    return shifts
