"""Objectives for models."""

from __future__ import annotations

from typing import Any, Dict

from ortools.sat.python import cp_model

import excelshifts.state as state


def maximize_total_coverage(
    model: cp_model.CpModel,
    instance: state.Instance,
    shifts: Dict[tuple[int, int, int], Any],
) -> None:
    """Set objective to maximize the total number of covered assignments.

    This matches the previous behavior: sum all X[i,j,k] over residents, days,
    and shift types.
    """
    model.Maximize(
        sum(
            shifts[(i, j, k)]
            for i, _ in enumerate(instance.residents)
            for j, _ in enumerate(instance.days)
            for k, _ in enumerate(state.ShiftType)
        )
    )
