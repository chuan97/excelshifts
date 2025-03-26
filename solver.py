"""Module to implement the contraint programming routine"""

from ortools.sat.python import cp_model

import state


def solve_shifts(
    residents: list[state.Resident],
    days: list[state.Day],
    v_positions: list[tuple[int, int]],
    totals: list[list[int]],
) -> list[tuple[int, int]]:
    """Asign shifts to residents and days

    Args:
        residents: The list of residents
        days: The list of days
        v_positions: The list of restricted (resident, day) tuples
        totals : The list of current totals for each resident and shift type

    Returns:
        A matrix of shifts for each resident and day, rows are residents and columns are days
    """

    model = cp_model.CpModel()

    # Create the variables
    shifts = (
        {}
    )  # shifts[(i, j, k)] = 1 if resident i is assigned to day j with shift type k
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")

    # TODO: Create the constraints
