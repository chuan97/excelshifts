"""Module to implement the contraint programming routine"""

import math
from operator import add

import numpy as np
from ortools.sat.python import cp_model

import excel
import state

# TODO: maximimar cobertura de tipos de guardia en función coste
# TODO: dividir en dos fases, primero check de los R4, señalando normas incumplidas para poder subsanar o ignorar
#   despues aplicar las optimización al resto de residentes.
# TODO: quitar exenciones, reprogramar rotantes externos
# TODO: R4s do only the preset shifts and no others


def solve_shifts(
    residents: list[state.Resident],
    days: list[state.Day],
    v_positions: list[tuple[int, int]],
    u_positions: list[tuple[int, int]],
    ut_positions: list[tuple[int, int]],
    p_positions: list[tuple[int, int]],
    presets: list[tuple[int, int, int]],
    totals: list[list[int]],
) -> list[list[str]]:
    """Asign shifts to residents and days

    Args:
        residents: The list of residents
        days: The list of days
        v_positions: The list of restricted (resident, day) tuples
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        ut_positions: The list of restricted (resident, day) tuples due to having afternoon emergencies shifts
        p_positions: The list of (resident, day) tuples indicating holidays and who covers them
        presets: The list of preset shifts as (resident, day, shift) tuples
        totals : The list of current totals for each resident and shift type_

    Returns:
        A matrix of shifts for each resident and day, rows are residents and columns are days
    """

    end_of_month = detect_end_of_month(days)
    emergencies = compute_emergency_shifts(u_positions, ut_positions, residents)
    excused_shifts = compute_excused_shifts(v_positions)
    p_days = compute_p_days(p_positions)

    model = cp_model.CpModel()

    # ------ CREATE THE VARIABLES ------

    # shifts[(i, j, k)] = 1 if resident i is assigned to day j with shift type_ k
    shifts = {}
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")

    # ------ CREATE THE CONSTRAINTS ------

    # --- discarded constraints ---

    # # Every shift type_ is covered by one resident every day except for R on the weekend
    # for k, _ in enumerate(state.ShiftType):
    #     for j, day in enumerate(days):
    #         if day.day_of_week not in ["V", "S", "D"] or k != state.ShiftType.R:
    #             model.add_exactly_one(
    #                 shifts[(i, j, k)] for i, _ in enumerate(residents)
    #             )

    # # each resident other than R4s does at most one shift on thursday to promote equidistribution
    # for i, resident in enumerate(residents):
    #     if resident != "R4":
    #         model.add_at_most_one(
    #             shifts[(i, j, k)]
    #             for j, day in enumerate(days)
    #             if day.day_of_week == "J" and j < end_of_month
    #             for k, _ in enumerate(state.ShiftType)
    #         )

    # # R3s work one and only one weekend shift
    # for i, resident in enumerate(residents):
    #     if resident.rank == "R3":
    #         model.add_exactly_one(
    #             shifts[(i, j, k)]
    #             for j, day in enumerate(days)
    #             if day.day_of_week in ["S", "D"] and j < end_of_month
    #             for k, _ in enumerate(state.ShiftType)
    #         )

    # --- basic constraints ---

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

    # If a resident is restricted a given day, they cannot do a shift that day
    for i, j in v_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)

    # No R type_ shifts on the weekend or holiday
    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week in ["S", "D"] or j in p_days:
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

    # If there are preset shifts, enforce those
    for preset in presets:
        model.add(shifts[preset] == 1)

    # # R4s do not do any shifts other than the preset ones
    # for i, j, k in presets:
    #     if residents[i].rank == "R4":
    #         for j_ in range(len(days)):
    #             for k_ in range(len(state.ShiftType)):
    #                 if (j_, k_) != (j, k):
    #                     model.add(shifts[(i, j_, k_)] == 0)

    # --- constraints that reflect rules of the hospital ---
    # TODO: consider exemptions
    # # R1s and R2s work at least one weekend shift
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R1", "R2"]:
    #         model.add_at_least_one(
    #             shifts[(i, j, k)]
    #             for j, day in enumerate(days)
    #             if day.day_of_week in ["S", "D"] and j < end_of_month
    #             for k, _ in enumerate(state.ShiftType)
    #         )

    # Residents asigned to a holiday must do a shift that day
    for i, j in p_positions:
        model.add(sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)) == 1)

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

    # If a resident that is not R4 does a shift on a saturday, they cannot do a shift the following monday
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            for j, day in enumerate(days):
                if day.day_of_week == "S" and j < len(days) - 2:
                    for k, _ in enumerate(state.ShiftType):
                        for p, _ in enumerate(state.ShiftType):
                            model.add(shifts[(i, j + 2, p)] == 0).only_enforce_if(
                                shifts[(i, j, k)]
                            )

    # If an R1 or R2 had an emergencies shift on a saturday, they cannot do a shift the following monday
    for i, j in u_positions:
        if days[j].day_of_week == "S" and j < len(days) - 2:
            for k, _ in enumerate(state.ShiftType):
                model.add(shifts[(i, j + 2, k)] == 0)

    # Every resident does at least one shift of each type_ except R1s that do not do R and residents with two or more excused shifts (SHOULD BE ONLY THREE OR MORE, BUT THEN WE RUN INTO IMPOSSIBILITIES)
    for i, resident in enumerate(residents):
        if excused_shifts.get(i, 0) < 2:
            for k, type_ in enumerate(state.ShiftType):
                if resident.rank != "R1":
                    model.add_at_least_one(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    )
                elif type_ != state.ShiftType.R:
                    model.add_at_least_one(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    )
                else:
                    for j, _ in enumerate(days):
                        model.add(shifts[(i, j, k)] == 0)

    # # Every resident does at most two shifts of each type_
    # for i, _ in enumerate(residents):
    #     for k, _ in enumerate(state.ShiftType):
    #         model.add(
    #             sum(shifts[(i, j, k)] for j, _ in enumerate(days) if j < end_of_month)
    #             <= 2
    #         )

    # R1s and R2s do at most one shift of type_s R and T
    for i, resident in enumerate(residents):
        if resident.rank in ["R1", "R2"]:
            for k, type_ in enumerate(state.ShiftType):
                if type_ in [state.ShiftType.R, state.ShiftType.T]:
                    model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # R3s do at most one shift of type_ G and M
    for i, resident in enumerate(residents):
        if resident.rank == "R3":
            for k, type_ in enumerate(state.ShiftType):
                if type_ in [state.ShiftType.G, state.ShiftType.M]:
                    model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

    # # R3s and R4s do exactly six shifts unless they have excuses due to restrictions
    # for i, resident in enumerate(residents):
    #     if resident.rank in ["R3", "R4"]:
    #         excuses = excused_shifts.get(i, 0)
    #         model.add(
    #             sum(
    #                 shifts[(i, j, k)]
    #                 for j, _ in enumerate(days)
    #                 if j < end_of_month
    #                 for k, _ in enumerate(state.ShiftType)
    #             )
    #             == 6 - excuses
    #         )

    # R2s do exactly six shifts after counting their emergencies shifts and excuses
    for i, resident in enumerate(residents):
        if resident.rank == "R2":
            excuses = excused_shifts.get(i, 0)
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6 - excuses - int(emergencies[i])
            )

    # R1s do between 5.5 and 6.5 shifts after counting their emergencies shifts
    # and excuses
    for i, resident in enumerate(residents):
        if resident.rank == "R1":
            excuses = excused_shifts.get(i, 0)
            if int(emergencies[i]) == emergencies[i]:
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                        for k, _ in enumerate(state.ShiftType)
                    )
                    == 6 - excuses - int(emergencies[i])
                )
            else:
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                        for k, _ in enumerate(state.ShiftType)
                    )
                    >= 6 - math.ceil(emergencies[i]) - excuses
                )
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                        for k, _ in enumerate(state.ShiftType)
                    )
                    <= 6 - math.floor(emergencies[i]) - excuses
                )

    # --- quality of life constraints ---

    # no resident other than R4s can have more than 2 shifts in 6 days (triplete)
    n = 6
    m = 2
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            for j in range(len(days) - n):
                model.add(
                    sum(
                        shifts[(i, j + m, k)]
                        for k, _ in enumerate(state.ShiftType)
                        for m in range(n)
                    )
                    <= m
                )

    # ------ OBJECTIVE FUNCTION ------

    # Minimize the difference between the total number of shifts of each type for each resident
    # Establish the two shift types with the least total number as preferences for each resident
    preferences = []
    for i, _ in enumerate(residents):
        sorted_totals = np.argsort(totals[i])
        preferences.append(list(sorted_totals[:2]))

    for i, _ in enumerate(residents):
        for k in preferences[i]:
            model.maximize(sum(shifts[(i, j, k)] for j, _ in enumerate(days)))

    # ------ SOLVE THE MODEL ------

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

    print(f"No solution found. Status: {status}")
    return None


def detect_end_of_month(days: list[state.Day]) -> int:
    """Detect the last day of the month if days beyond that point are considered

    Args:
        days: The list of days

    Returns:
        The index of the last day of the month in the list of days
    """

    end_of_month = len(days)
    for i in range(1, len(days)):
        if days[i].number < days[i - 1].number:
            end_of_month = i
            break

    return end_of_month


def compute_emergency_shifts(
    u_positions: list[tuple[int, int]],
    ut_positions: list[tuple[int, int]],
    residents: list[state.Resident],
) -> list[int]:
    """Compute number of emergency shifts done by each resident

    Args:
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        ut_positions: The list of restricted (residen, day) tuples due to having afternoon emergencies shifts
        residents: The list of residents

    Returns:
        A list with the number of emergencies for each resident
    """

    # from u_positions, compute the number of emergency shifts for each resident
    emergencies = [0.0] * len(residents)
    for i, _ in u_positions:
        emergencies[i] += 1.0

    # from ut_positions, compute the number of afternoon emergency shifts for each resident
    for i, _ in ut_positions:
        emergencies[i] += 0.5

    return emergencies


def compute_excused_shifts(v_positions: list[tuple[int, int]]) -> dict[int, int]:
    """Compute the number of five-day vacation streaks for each resident

    Args:
        v_positions: The list of restricted (resident, day) tuples

    Returns:
        A dictionary with the (resident, excuses) pairs
    """

    # from v_positions which is sorted by resident and day within resident, compute the number of five-day vacation streaks for each resident
    last_i = v_positions[0][0]
    last_j = -1
    count = 1
    excused_shifts = {}
    for i, j in v_positions:
        if i != last_i:
            excuses = count // 5
            if excuses:
                excused_shifts[last_i] = excuses
            last_i = i
            count = 1

        if j == last_j + 1:
            count += 1

        last_j = j

    return excused_shifts


def compute_p_days(p_positions: list[tuple[int, int]]) -> set[int]:
    """Compute the set of days that are holidays

    Args:
        p_positions: The list of (resident, day) tuples indicating holidays and who covers them
    Returns:
        A set of days that are holidays
    """

    return set(day for _, day in p_positions)


if __name__ == "__main__":
    f_path = "data/Guardias enero presets rot ext.xlsx"
    sheet_name = "Enero 2025"

    row_start = 4
    col_start = 3
    n_residents = 21
    n_days = 33

    residents = excel.load_residents(f_path, sheet_name, row_start, n_residents)
    days = excel.load_days(f_path, sheet_name, col_start, n_days)
    v_positions = excel.load_restrictions(
        f_path, sheet_name, "V", row_start, col_start, n_residents, n_days
    )
    u_positions = excel.load_restrictions(
        f_path, sheet_name, "U", row_start, col_start, n_residents, n_days
    )
    ut_positions = excel.load_restrictions(
        f_path, sheet_name, "UT", row_start, col_start, n_residents, n_days
    )
    totals = excel.load_totals(f_path, "Global", 3, 2, n_residents)
    preset_shifts = excel.load_preset_shifts(
        f_path, sheet_name, row_start, col_start, n_residents, n_days
    )

    shifts_matrix = solve_shifts(
        residents, days, v_positions, u_positions, ut_positions, preset_shifts, totals
    )
    print(shifts_matrix)
    f_path_out = excel.copy_excel_file(f_path, "_solved")
    excel.save_shifts(f_path_out, sheet_name, shifts_matrix, row_start, col_start)
