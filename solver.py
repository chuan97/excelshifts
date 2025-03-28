"""Module to implement the contraint programming routine"""

import math
from operator import add

import numpy as np
from ortools.sat.python import cp_model

import excel
import state

# TODO: cada 5/7 dias de vacaciones se hace una guardia menos
# TODO: los R4s se ponen sus propias guardias y en general puede haber gente que se haya fijado guardias
# TODO: maximimar cobertura de tipos de guardia en función coste


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

    # detect end of month
    end_of_month = len(days)
    for i in range(1, len(days)):
        if days[i].number < days[i - 1].number:
            end_of_month = i
            break

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

    # # Create the constraints
    # # Every shift type_ is covered by one resident every day except for R on the weekend
    # for k, _ in enumerate(state.ShiftType):
    #     for j, day in enumerate(days):
    #         if day.day_of_week not in ["V", "S", "D"] or k != state.ShiftType.R:
    #             model.add_exactly_one(
    #                 shifts[(i, j, k)] for i, _ in enumerate(residents)
    #             )

    # Every shift type is covered by at most one resident each day
    for j, _ in enumerate(days):
        for k, _ in enumerate(state.ShiftType):
            model.add_at_most_one(shifts[(i, j, k)] for i, _ in enumerate(residents))

    # Every resident has at most one shift per day
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            model.add_at_most_one(
                shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)
            )

    # R1s and R2s work at least one weekend shift
    for i, resident in enumerate(residents):
        if resident.rank not in ["R3", "R4"]:
            model.add_at_least_one(
                shifts[(i, j, k)]
                for j, day in enumerate(days)
                if day.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            )

    # R3s and R4s work one and only one weekend shift
    for i, resident in enumerate(residents):
        if resident.rank in ["R3", "R4"]:
            model.add_exactly_one(
                shifts[(i, j, k)]
                for j, day in enumerate(days)
                if day.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            )

    # If a resident does a friday shift of a type different thank R they must do the following sunday shift
    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week == "V":
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for k, type_ in enumerate(state.ShiftType)
                        if type_ != state.ShiftType.R
                    )
                    == sum(shifts[(i, j + 2, k)] for k, _ in enumerate(state.ShiftType))
                )

    # but the sunday shift must be a different type_ than the friday shift
    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week == "V":
                for k, type_ in enumerate(state.ShiftType):
                    model.add(shifts[(i, j + 2, k)] == 0).only_enforce_if(
                        shifts[(i, j, k)]
                    )

    # Actually no R type_ shifts on the weekend (MAY NEED TO BE RELAXED)
    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week in ["S", "D"]:
                for k, type_ in enumerate(state.ShiftType):
                    if type_ == state.ShiftType.R:
                        model.add(shifts[(i, j, k)] == 0)

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

    # Every resident does at least one shift of each type_ except R1s that do not do R
    for i, resident in enumerate(residents):
        for k, type_ in enumerate(state.ShiftType):
            if resident.rank != "R1":
                model.add_at_least_one(
                    shifts[(i, j, k)] for j, _ in enumerate(days) if j < end_of_month
                )
            elif type_ != state.ShiftType.R:
                model.add_at_least_one(
                    shifts[(i, j, k)] for j, _ in enumerate(days) if j < end_of_month
                )
            else:
                for j, _ in enumerate(days):
                    model.add(shifts[(i, j, k)] == 0)

    # Every resident does at most two shifts of each type_
    for i, _ in enumerate(residents):
        for k, _ in enumerate(state.ShiftType):
            model.add(
                sum(shifts[(i, j, k)] for j, _ in enumerate(days) if j < end_of_month)
                <= 2
            )

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

    # R3s and R4s do exactly six shifts
    for i, resident in enumerate(residents):
        if resident.rank in ["R3", "R4"]:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6
            )

    # R1s and R2s do between 5.5 and 6 shifts after counting their emergencies shifts
    for i, resident in enumerate(residents):
        if resident.rank in ["R1", "R2"]:
            model.add(
                math.floor(5 - emergencies[i])
                < sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
            )
            model.add(
                math.floor(6 - emergencies[i])
                >= sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
            )

    # each resident does at least on shift on thursday
    for i, _ in enumerate(residents):
        model.add_at_most_one(
            shifts[(i, j, k)]
            for j, day in enumerate(days)
            if day.day_of_week == "J" and j < end_of_month
            for k, _ in enumerate(state.ShiftType)
        )

    # no resident can have more than 2 shifts in 6 days (triplete)
    n = 6
    m = 2
    for i, _ in enumerate(residents):
        for j in range(len(days) - n):
            model.add(
                sum(
                    shifts[(i, j + m, k)]
                    for k, _ in enumerate(state.ShiftType)
                    for m in range(n)
                )
                <= m
            )

    # If a resident is restricted a given day, they cannot do a shift that day
    for i, j in v_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)

    # If a resident has an emergency shift, they cannot do a shift that day or the next
    for i, j in u_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)
            if j < len(days) - 1:
                model.add(shifts[(i, j + 1, k)] == 0)

    # If a resident has an afternoon emergency shift, they cannot do a shift that day or the day before
    for i, j in ut_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)
            if j > 0:
                model.add(shifts[(i, j - 1, k)] == 0)

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
    excel.copy_excel_file(
        "data/Guardias enero simple.xlsx", "Guardias enero simple_solved.xlsx"
    )
    excel.save_shifts(
        "data/Guardias enero simple_solved.xlsx", "Enero 2025", shifts_matrix
    )
