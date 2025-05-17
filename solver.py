"""Module to implement the contraint programming routine"""

import math

from ortools.sat.python import cp_model

import state

# TODO: dividir en dos fases, primero check de los R4, señalando normas incumplidas para poder subsanar o ignorar
#   despues aplicar las optimización al resto de residentes.
# TODO: Totals is not updated in the input excel so it is useless


def solve_shifts(
    residents: list[state.Resident],
    days: list[state.Day],
    v_positions: list[tuple[int, int]],
    u_positions: list[tuple[int, int]],
    ut_positions: list[tuple[int, int]],
    p_positions: list[tuple[int, int]],
    external_rotations: set[int],
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
        external_rotations: The set of residents who are in external rotations
        presets: The list of preset shifts as (resident, day, shift) tuples
        totals : The list of current totals for each resident and shift type_

    Returns:
        A matrix of shifts for each resident and day, rows are residents and columns are days
    """

    end_of_month = detect_end_of_month(days)
    emergencies = compute_emergency_shifts(u_positions, ut_positions, residents)
    p_days = compute_p_days(p_positions)
    weekend_emergencies = compute_weekend_emergencies(u_positions, days, p_days)

    model = cp_model.CpModel()

    # ------ CREATE THE VARIABLES ------

    # shifts[(i, j, k)] == 1 if resident i is assigned to day j with shift type k
    shifts = {}
    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                shifts[(i, j, k)] = model.NewBoolVar(f"shift_{i}_{j}_{k}")

    # ------ CREATE THE CONSTRAINTS ------

    # --- basic (physical) constraints ---

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

    # If a resident has an emergency shift, they cannot do a shift that day nor the next or the previous day
    for i, j in u_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)
            if 0 < j < len(days) - 1:
                model.add(shifts[(i, j + 1, k)] == 0)
                model.add(shifts[(i, j - 1, k)] == 0)

    # If a resident has an afternoon emergency shift, they cannot do a shift that day or the day before
    for i, j in ut_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0)
            if j > 0:
                model.add(shifts[(i, j - 1, k)] == 0)

    # If a resident is in an external rotation, they cannot do any shifts
    for i in external_rotations:
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                model.add(shifts[(i, j, k)] == 0)

    # --- constraints that reflect rules of the hospital ---

    # - about the coverage of shifts -

    # Every shift type is covered by at most one resident each day
    for j, _ in enumerate(days):
        for k, _ in enumerate(state.ShiftType):
            model.add_at_most_one(shifts[(i, j, k)] for i, _ in enumerate(residents))

    # In any given day, either G or T must be covered
    for j, day in enumerate(days):
        # WARNING: this constraint is specific to this month
        if day.number != 27:
            model.add_at_least_one(
                shifts[(i, j, k)]
                for i, _ in enumerate(residents)
                for k, type_ in enumerate(state.ShiftType)
                if type_.name in ["G", "T"]
            )

    # # At most only two types of shift can be uncovered each day
    # for j, day in enumerate(days):
    #     model.add(
    #         sum(
    #             shifts[(i, j, k)]
    #             for i, _ in enumerate(residents)
    #             for k, _ in enumerate(state.ShiftType)
    #         )
    #         > (1 if day.day_of_week in ["V", "S", "D"] or j in p_days else 2)
    #     )

    # The same type cannot be uncovered both days of a weekend
    for j, day in enumerate(days):
        if day.day_of_week == "S" and j < len(days) - 1:
            for k, type_ in enumerate(state.ShiftType):
                if type_.name != "R":
                    model.add_at_least_one(
                        [shifts[(i, j, k)] for i, _ in enumerate(residents)]
                        + [shifts[(i, j + 1, k)] for i, _ in enumerate(residents)]
                    )

    # TODO: should be a softer constraint, where there is only R on Fridays if every other day is covered
    # No R on Fridays
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            for j, day in enumerate(days):
                if day.day_of_week == "V":
                    for k, type_ in enumerate(state.ShiftType):
                        if type_.name == "R":
                            model.add(shifts[(i, j, k)] == 0)

    # - about the number of shifts -

    # Enforce presets, and no other shifts for R4s
    for i, resident in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                if (i, j, k) in presets:
                    model.add(shifts[(i, j, k)] == 1)
                elif resident.rank == "R4":
                    model.add(shifts[(i, j, k)] == 0)

    # Residents asigned to a holiday must do a shift that day
    for i, j in p_positions:
        model.add(sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)) == 1)

    # R3s do exactly six shifts unless they are in an external rotation
    for i, resident in enumerate(residents):
        if resident.rank == "R3" and i not in external_rotations:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6
            )

    # R2s do exactly six shifts after counting their emergencies shifts
    # unless they are in an external rotation
    for i, resident in enumerate(residents):
        if resident.rank == "R2" and i not in external_rotations:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6 - int(emergencies[i])
            )

    # # R1s do between 5.5 and 6.5 shifts after counting their emergencies shifts
    # # unless they are in an external rotation
    # for i, resident in enumerate(residents):
    #     if resident.rank == "R1" and i not in external_rotations:
    #         if int(emergencies[i]) == emergencies[i]:
    #             model.add(
    #                 sum(
    #                     shifts[(i, j, k)]
    #                     for j, _ in enumerate(days)
    #                     if j < end_of_month
    #                     for k, _ in enumerate(state.ShiftType)
    #                 )
    #                 == 6 - int(emergencies[i])
    #             )
    #         else:
    #             model.add(
    #                 sum(
    #                     shifts[(i, j, k)]
    #                     for j, _ in enumerate(days)
    #                     if j < end_of_month
    #                     for k, _ in enumerate(state.ShiftType)
    #                 )
    #                 >= 6 - math.ceil(emergencies[i])
    #             )
    #             model.add(
    #                 sum(
    #                     shifts[(i, j, k)]
    #                     for j, _ in enumerate(days)
    #                     if j < end_of_month
    #                     for k, _ in enumerate(state.ShiftType)
    #                 )
    #                 <= 6 - math.floor(emergencies[i])
    #             )

    # # - about the distribution of shifts -

    # Every resident does at least one shift of each type_
    # except R1s that do not do R and residents in external rotations
    for i, resident in enumerate(residents):
        if i not in external_rotations and resident.rank != "R4":
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

    # Every non R4 resident does at most two shifts of each type_
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            for k, _ in enumerate(state.ShiftType):
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    )
                    <= 2
                )

    # # - about the weekend shifts -

    # TODO: que sea todo el mundo
    # R1s and R2s work at least one weekend shift unless they are in an external rotation
    for i, resident in enumerate(residents):
        if resident.rank in ["R1", "R2"] and i not in external_rotations:
            model.add_at_least_one(
                shifts[(i, j, k)]
                for j, day in enumerate(days)
                if day.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            )

    # Friday -> Sunday
    # If a resident does a friday shift of a type different than R they must do the following sunday shift
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            for j, day in enumerate(days):
                # WARNING: this constraint is specific to this month
                if day.day_of_week == "V" and day.number != 27:
                    model.add(
                        sum(
                            shifts[(i, j, k)]
                            for k, type_ in enumerate(state.ShiftType)
                            if type_ != state.ShiftType.R
                        )
                        == sum(
                            shifts[(i, j + 2, k)] for k, _ in enumerate(state.ShiftType)
                        )
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

    # --- quality of life constraints ---

    # # no resident other than R4s can have more than 2 shifts in 6 days (triplete)
    # n = 6
    # m = 2
    # for i, resident in enumerate(residents):
    #     if resident.rank != "R4":
    #         for j in range(len(days) - n):
    #             n_u_shifts = compute_n_u_shifts_in_window(u_positions, i, j, n)

    #             model.add(
    #                 sum(
    #                     shifts[(i, j + j_, k)]
    #                     for k, _ in enumerate(state.ShiftType)
    #                     for j_ in range(n)
    #                 )
    #                 <= m - n_u_shifts
    #             )

    # # TODO: tener en cuenta urgencias y viernes
    # # no resident other than R4s can work more than 2 weekends or holidays in a month
    # for i, resident in enumerate(residents):
    #     if resident.rank != "R4":
    #         model.add(
    #             sum(
    #                 shifts[(i, j, k)]
    #                 for j, day in enumerate(days)
    #                 if day.day_of_week in ["S", "D"] or j in p_days and j < end_of_month
    #                 for k, _ in enumerate(state.ShiftType)
    #             )
    #             <= 2 - weekend_emergencies.get(i, 0)
    #         )

    # no resident other than R4s can work more than 1 sunday (i.e. friday + sunday combo)
    for i, resident in enumerate(residents):
        if resident.rank != "R4":
            model.add(
                sum(
                    shifts[i, j, k]
                    for j, day in enumerate(days)
                    if day.day_of_week == "D" and j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                <= 1
            )

    # ------ OBJECTIVE FUNCTIONS ------

    # # Minimize the difference between the total number of shifts of each type for each resident
    # # I.e. establish the two shift types with the least total number as preferences for each resident
    # preferences = []
    # for i, _ in enumerate(residents):
    #     sorted_totals = np.argsort(totals[i])
    #     preferences.append(list(sorted_totals[:2]))

    # for i, _ in enumerate(residents):
    #     for k in preferences[i]:
    #         model.maximize(sum(shifts[(i, j, k)] for j, _ in enumerate(days)))

    # Maximize the number of covered shifts
    for j, day in enumerate(days):
        for k, type_ in enumerate(state.ShiftType):
            model.maximize(sum(shifts[(i, j, k)] for i, _ in enumerate(residents)))

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


def compute_p_days(p_positions: list[tuple[int, int]]) -> set[int]:
    """Compute the set of days that are holidays

    Args:
        p_positions: The list of (resident, day) tuples indicating holidays and who covers them
    Returns:
        A set of days that are holidays
    """

    return set(day for _, day in p_positions)


def compute_weekend_emergencies(
    u_positions: list[tuple[int, int]],
    days: list[state.Day],
    p_days: set[int],
) -> dict[int, int]:
    """Compute the number of weekend or holiday emergencies for each resident

    Args:
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        days: The list of days
        p_days: The set of days that are holidays

    Returns:
        A dictionary with the number of weekend emergencies for each resident
    """

    weekend_emergencies = {}
    for i, j in u_positions:
        if (
            days[j].day_of_week in ["V", "S", "D"]
            or j in p_days
            and (i, j - 2) not in u_positions
        ):
            weekend_emergencies[i] = weekend_emergencies.get(i, 0) + 1

    return weekend_emergencies


def compute_n_u_shifts_in_window(
    u_positions: list[tuple[int, int]], i: int, j: int, win_size: int
) -> int:
    """Compute the number of emergency shifts in a given window for a resident

    Args:
        u_positions: The list of restricted (resident, day) tuples due to having emergencies shifts
        i: The resident index
        j: The day index
        window_size: The size of the window of days from j onward

    Returns:
        The number of emergency shifts in the given window for the resident
    """

    return sum(1 for j_ in range(win_size) if (i, j + j_) in u_positions)


# --- discarded constraints ---

# # Every shift type_ is covered by one resident every day except for R on the weekend and holidays
# for k, _ in enumerate(state.ShiftType):
#     for j, day in enumerate(days):
#         if (
#             day.day_of_week not in ["S", "D"] and j not in p_days
#         ) or k != state.ShiftType.R:
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

# # R1s and R2s do at most one shift of type_s R and T
# for i, resident in enumerate(residents):
#     if resident.rank in ["R1", "R2"]:
#         for k, type_ in enumerate(state.ShiftType):
#             if type_ in [state.ShiftType.R, state.ShiftType.T]:
#                 model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))

# # R3s do at most one shift of type_ G and M
# for i, resident in enumerate(residents):
#     if resident.rank == "R3":
#         for k, type_ in enumerate(state.ShiftType):
#             if type_ in [state.ShiftType.G, state.ShiftType.M]:
#                 model.add_at_most_one(shifts[(i, j, k)] for j, _ in enumerate(days))
