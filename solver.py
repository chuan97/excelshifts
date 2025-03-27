"""Module to implement the contraint programming routine"""

from ortools.sat.python import cp_model

import state


def solve_shifts(
    residents: list[state.Resident],
    days: list[state.Day],
    v_positions: list[tuple[int, int]],
    u_positions: list[tuple[int, int]],
    ut_positions: list[tuple[int, int]],
    totals: list[list[int]],
) -> list[tuple[int, int]]:
    """Asign shifts to residents and days

    Args:
        residents: The list of residents
        days: The list of days
        v_positions: The list of restricted (resident, day) tuples
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        totals : The list of current totals for each resident and shift type

    Returns:
        A matrix of shifts for each resident and day, rows are residents and columns are days
    """

    # from u_positions, compute the number of emergency shifts for each resident
    emergencies = [0] * len(residents)
    for i, j in u_positions:
        emergencies[i] += 1

    # from ut_positions, compute the number of afternoon emergency shifts for each resident
    for i, j in ut_positions:
        emergencies[i] += 0.5

    model = cp_model.CpModel()

    # Create the variables
    shifts = (
        {}
    )  # shifts[(i, j, k)] = 1 if resident i is assigned to day j with shift type k
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")

    # Create the constraints
    # Every shift type is covered by one resident every day
    for k, _ in enumerate(state.ShiftType):
        for j, _ in enumerate(days):
            model.add_exactly_one(shifts[(i, j, k)] for i, _ in enumerate(residents))

    # Every resident has at most one shift per day
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            model.add_at_most_one(
                shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)
            )

    # R1s and R2s work at least one weekend shift
    for i, _ in enumerate(residents):
        if resident.rank not in ["R3", "R4"]:
            model.add_at_least_one(
                shifts[(i, j, k)]
                for j, _ in enumerate(days)
                if days[j].day_of_week in ["S", "D"]
                for k, _ in enumerate(state.ShiftType)
            )

    # R3s and R4s work one and only one weekend shift
    for i, resident in enumerate(residents):
        if resident.rank in ["R3", "R4"]:
            model.add_exactly_one(
                shifts[(i, j, k)]
                for j, _ in enumerate(days)
                if days[j].day_of_week in ["S", "D"]
                for k, _ in enumerate(state.ShiftType)
            )

    # If a resident does a friday shift in anything but R, they must do the following sunday shift
    for i, resident in enumerate(residents):
        for j, _ in enumerate(days):
            if days[j].day_of_week == "V":
                for k, typeA in enumerate(state.ShiftType):
                    if typeA != state.ShiftType.R and shifts[(i, j, k)]:
                        model.add_exactly_one(
                            shifts[(i, j + 2, p)]
                            for p, typeB in enumerate(state.ShiftType)
                            if typeA != typeB
                        )

    # Actually no R type shifts on the weekend (MAY NEED TO BE RELAXED)
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            if days[j].day_of_week in ["V", "S", "D"]:
                for k, type in enumerate(state.ShiftType):
                    if type == state.ShiftType.R:
                        model.add(shifts[(i, j, k)] == 0)

    # If a resident does a shift on a day, they cannot do a shift on the following day
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            if j < len(days) - 1:
                for k, _ in enumerate(state.ShiftType):
                    if shifts[(i, j, k)]:
                        for p, _ in enumerate(state.ShiftType):
                            model.add(shifts[(i, j + 1, p)] == 0)

    # If a resident does a shift on a saturday, they cannot do a shift the following monday
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            if days[j].day_of_week == "S":
                for k, _ in enumerate(state.ShiftType):
                    if shifts[(i, j, k)]:
                        for p, _ in enumerate(state.ShiftType):
                            model.add(shifts[(i, j + 2, p)] == 0)

    # Every resident does at least one shift of each type
    for i, _ in enumerate(residents):
        for k, _ in enumerate(state.ShiftType):
            model.add_at_least_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # R1s and R2s do at most one shift of types R and T
    for i, resident in enumerate(residents):
        if resident.rank in ["R1", "R2"]:
            for k, type in enumerate(state.ShiftType):
                if type in [state.ShiftType.R, state.ShiftType.T]:
                    model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # R3s and R4s do at most one shift of type G and M
    for i, resident in enumerate(residents):
        if resident.rank in ["R3", "R4"]:
            for k, type in enumerate(state.ShiftType):
                if type in [state.ShiftType.G, state.ShiftType.M]:
                    model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # R3s and R4s do exactly six shifts
    for i, resident in enumerate(residents):
        if resident.rank in ["R3", "R4"]:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6
            )

    # R1s and R2s do between 5.5 and 6 shifts after counting their emergencies shifts
    for i, resident in enumerate(residents):
        if resident.rank in ["R1", "R2"]:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    for k, _ in enumerate(state.ShiftType)
                )
                + emergencies[i]
                >= 5.5
            )
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    for k, _ in enumerate(state.ShiftType)
                )
                + emergencies[i]
                <= 6
            )

    # If a resident is restricted a given day, they cannot do a shift that day
    for i, j in v_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)

    # If a resident has an emergency shift, they cannot do a shift that day
    for i, j in u_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)

    # If a resident has an afternoon emergency shift, they cannot do a shift that day
    for i, j in ut_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)

    # TODO: Add the cost function
