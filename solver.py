"""Module to implement the contraint programming routine"""

import math
from operator import add

import numpy as np
from ortools.sat.python import cp_model

import excel
import state


def solve_shifts(
    residents: list[state.Resident],
    days: list[state.Day],
    v_positions: list[tuple[int, int]],
    u_positions: list[tuple[int, int]],
    ut_positions: list[tuple[int, int]],
    totals: list[list[int]],
) -> list[list[str]]:
    """Asign shifts to residents and days

    Args:
        residents: The list of residents
        days: The list of days
        v_positions: The list of restricted (resident, day) tuples
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        totals : The list of current totals for each resident and shift type_

    Returns:
        A matrix of shifts for each resident and day, rows are residents and columns are days
    """

    # from u_positions, compute the number of emergency shifts for each resident
    emergencies = [0.0] * len(residents)
    for i, j in u_positions:
        emergencies[i] += 1.0

    # from ut_positions, compute the number of afternoon emergency shifts for each resident
    for i, j in ut_positions:
        emergencies[i] += 0.5

    model = cp_model.CpModel()

    # Create the variables
    # shifts[(i, j, k)] = 1 if resident i is assigned to day j with shift type_ k
    shifts = {}
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")

    # Create the constraints
    # Every shift type_ is covered by one resident every day
    for k, _ in enumerate(state.ShiftType):
        for j, _ in enumerate(days):
            model.add_exactly_one(shifts[(i, j, k)] for i, _ in enumerate(residents))

    # Every resident has at most one shift per day
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            model.add_at_most_one(
                shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)
            )

    # # R1s and R2s work at least one weekend shift
    # for i, resident in enumerate(residents):
    #     if resident.rank not in ["R3", "R4"]:
    #         model.add_at_least_one(
    #             shifts[(i, j, k)]
    #             for j, day in enumerate(days)
    #             if day.day_of_week in ["S", "D"]
    #             for k, _ in enumerate(state.ShiftType)
    #         )

    # # R3s and R4s work one and only one weekend shift
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R3", "R4"]:
    #         model.add_exactly_one(
    #             shifts[(i, j, k)]
    #             for j, day in enumerate(days)
    #             if day.day_of_week in ["S", "D"]
    #             for k, _ in enumerate(state.ShiftType)
    #         )

    # # If a resident does a friday shift in anything but R, they must do the following sunday shift
    # for i, resident in enumerate(residents):
    #     for j, day in enumerate(days):
    #         if day.day_of_week == "V":
    #             for k, type_A in enumerate(state.ShiftType):
    #                 if type_A != state.ShiftType.R:
    #                     model.add_exactly_one(
    #                         shifts[(i, j + 2, p)]
    #                         for p, type_B in enumerate(state.ShiftType)
    #                         if type_A != type_B
    #                     ).only_enforce_if(shifts[(i, j, k)])

    # # Actually no R type_ shifts on the weekend (MAY NEED TO BE RELAXED)
    # for i, _ in enumerate(residents):
    #     for j, day in enumerate(days):
    #         if day.day_of_week in ["V", "S", "D"]:
    #             for k, type_ in enumerate(state.ShiftType):
    #                 if type_ == state.ShiftType.R:
    #                     model.add(shifts[(i, j, k)] == 0)

    # If a resident does a shift on a day, they cannot do a shift on the following day
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            if j < len(days) - 1:
                for k, _ in enumerate(state.ShiftType):
                    for p, _ in enumerate(state.ShiftType):
                        model.add(shifts[(i, j + 1, p)] == 0).only_enforce_if(
                            shifts[(i, j, k)]
                        )

    # If a resident does a shift on a saturday, they cannot do a shift the following monday
    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week == "S" and j < len(days) - 2:
                for k, _ in enumerate(state.ShiftType):
                    for p, _ in enumerate(state.ShiftType):
                        model.add(shifts[(i, j + 2, p)] == 0).only_enforce_if(
                            shifts[(i, j, k)]
                        )

    # # Every resident does at least one shift of each type_
    # for i, _ in enumerate(residents):
    #     for k, _ in enumerate(state.ShiftType):
    #         model.add_at_least_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # # R1s and R2s do at most one shift of type_s R and T
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R1", "R2"]:
    #         for k, type_ in enumerate(state.ShiftType):
    #             if type_ in [state.ShiftType.R, state.ShiftType.T]:
    #                 model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # # R3s and R4s do at most one shift of type_ G and M
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R3", "R4"]:
    #         for k, type_ in enumerate(state.ShiftType):
    #             if type_ in [state.ShiftType.G, state.ShiftType.M]:
    #                 model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # # R3s and R4s do exactly six shifts
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R3", "R4"]:
    #         model.add(
    #             sum(
    #                 shifts[(i, j, k)]
    #                 for j, _ in enumerate(days)
    #                 for k, _ in enumerate(state.ShiftType)
    #             )
    #             == 6
    #         )

    # # R1s and R2s do between 5.5 and 6 shifts after counting their emergencies shifts
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R1", "R2"]:
    #         model.add(
    #             math.floor(5.5 - emergencies[i])
    #             < sum(
    #                 shifts[(i, j, k)]
    #                 for j, _ in enumerate(days)
    #                 for k, _ in enumerate(state.ShiftType)
    #             )
    #         )
    #         model.add(
    #             math.floor(6 - emergencies[i])
    #             >= sum(
    #                 shifts[(i, j, k)]
    #                 for j, _ in enumerate(days)
    #                 for k, _ in enumerate(state.ShiftType)
    #             )
    #         )

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

    # Objective function: minimize the difference between the total number of shifts of each type for each resident
    # Establish the two shift types with the least total number as preferences for each resident

    preferences = []
    for i, _ in enumerate(residents):
        sorted_totals = np.argsort(totals[i])
        preferences.append(list(sorted_totals[:2]))

    for i, _ in enumerate(residents):
        for k in preferences[i]:
            model.maximize(sum(shifts[(i, j, k)] for j, _ in enumerate(days)))

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL:
        shifts_matrix = []
        for i, resident in enumerate(residents):
            shifts_per_resident = []
            for j, day in enumerate(days):
                shift = ""
                for k, type_ in enumerate(state.ShiftType):
                    if solver.Value(shifts[(i, j, k)]):
                        shift = type_.name
                        break
                shifts_per_resident.append(shift)

            shifts_matrix.append(shifts_per_resident)

        return shifts_matrix
    else:
        print("No solution found")
        return None


if __name__ == "__main__":
    residents = excel.load_residents("data/Guardias enero.xlsx", "Enero 2025")
    days = excel.load_days("data/Guardias enero.xlsx", "Enero 2025")
    v_positions = excel.load_restrictions("data/Guardias enero.xlsx", "Enero 2025", "V")
    u_positions = excel.load_restrictions("data/Guardias enero.xlsx", "Enero 2025", "U")
    ut_positions = excel.load_restrictions(
        "data/Guardias enero.xlsx", "Enero 2025", "UT"
    )
    totals = excel.load_totals("data/Guardias enero.xlsx", "Global")
    print(len(residents), residents)
    print(len(days), days)
    print(len(v_positions), v_positions)
    print(len(u_positions), u_positions)
    print(len(ut_positions), ut_positions)
    print(len(totals), totals)
    shifts_matrix = solve_shifts(
        residents, days, v_positions, u_positions, ut_positions, totals
    )
    print(shifts_matrix)
    excel.copy_excel_file("data/Guardias enero.xlsx", "Guardias enero_solved.xlsx")
    excel.save_shifts("data/Guardias enero_solved.xlsx", "Enero 2025", shifts_matrix)
