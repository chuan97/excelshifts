from __future__ import annotations

import excelshifts.state as state

# ---------- Basic (physical) constraints ----------


def one_shift_per_day(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            lits = [shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)]
            if lits:
                model.Add(sum(lits) <= 1).OnlyEnforceIf(enable)
    return enable


def restricted_day_off(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    v_positions = instance.v_positions

    for i, j in v_positions:
        for k, _ in enumerate(state.ShiftType):
            model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
    return enable


def no_R_on_weekends_or_holidays(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    p_days = instance.p_days

    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week in ["S", "D"] or j in p_days:
                for k, t in enumerate(state.ShiftType):
                    if t == state.ShiftType.R:
                        model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
    return enable


def rest_after_any_shift(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for i, _ in enumerate(residents):
        # (works day j) + (works day j+1) <= 1
        for j, _ in enumerate(days):
            if j < len(days) - 1:
                model.Add(
                    sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType))
                    + sum(shifts[(i, j + 1, k)] for k, _ in enumerate(state.ShiftType))
                    <= 1
                ).OnlyEnforceIf(enable)
    return enable


def block_around_emergency_u(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    u_positions = instance.u_positions
    days = instance.days

    for i, j in u_positions:
        for k, _ in enumerate(state.ShiftType):
            model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
            if 0 < j < len(days) - 1:
                model.Add(shifts[(i, j + 1, k)] == 0).OnlyEnforceIf(enable)
                model.Add(shifts[(i, j - 1, k)] == 0).OnlyEnforceIf(enable)
    return enable


def block_around_emergency_ut(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    ut_positions = instance.ut_positions

    for i, j in ut_positions:
        for k, _ in enumerate(state.ShiftType):
            model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
            if j > 0:
                model.Add(shifts[(i, j - 1, k)] == 0).OnlyEnforceIf(enable)
    return enable


def external_rotation_off(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    external_rotations = instance.external_rotations
    days = instance.days

    for i, _ in enumerate(residents):
        if i in external_rotations:
            for j, _ in enumerate(days):
                for k, _ in enumerate(state.ShiftType):
                    model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
    return enable


# ---------- Coverage constraints ----------


def at_most_one_resident_per_shift_per_day(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for j, _ in enumerate(days):
        for k, _ in enumerate(state.ShiftType):
            lits = [shifts[(i, j, k)] for i, _ in enumerate(residents)]
            if lits:
                model.Add(sum(lits) <= 1).OnlyEnforceIf(enable)
    return enable


def cover_G_or_T_each_day(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for j, _ in enumerate(days):
        lits = [
            shifts[(i, j, k)]
            for i, _ in enumerate(residents)
            for k, t in enumerate(state.ShiftType)
            if t.name in ["G", "T"]
        ]
        if lits:
            model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
    return enable


def min_assignments_per_day(model, instance, shifts, spec):
    """Implements: 'At most two types of shift can be uncovered each day' using the
    original inequality present in solver.py.
    """
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    p_days = instance.p_days

    for j, day in enumerate(days):
        rhs = 1 if (day.day_of_week in ["V", "S", "D"] or j in p_days) else 2
        model.Add(
            sum(
                shifts[(i, j, k)]
                for i, _ in enumerate(residents)
                for k, _ in enumerate(state.ShiftType)
            )
            > rhs
        ).OnlyEnforceIf(enable)
    return enable


def not_same_type_uncovered_both_weekend_days(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for j, day in enumerate(days):
        if day.day_of_week == "S" and j < len(days) - 1:
            for k, t in enumerate(state.ShiftType):
                if t.name != "R":
                    w1 = [shifts[(i, j, k)] for i, _ in enumerate(residents)]
                    w2 = [shifts[(i, j + 1, k)] for i, _ in enumerate(residents)]
                    lits = w1 + w2
                    if lits:
                        model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
    return enable


# ---------- Number-of-shifts constraints ----------


def enforce_presets_and_R4_only_presets(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    presets = instance.presets

    for i, r in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                if (i, j, k) in presets:
                    model.Add(shifts[(i, j, k)] == 1).OnlyEnforceIf(enable)
                elif r.rank == "R4":
                    model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
    return enable


def holiday_assigned_must_work(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    p_positions = instance.p_positions

    for i, j in p_positions:
        model.Add(
            sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)) == 1
        ).OnlyEnforceIf(enable)
    return enable


def r1_r2_r3_exactly_six_minus_emergencies(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    end_of_month = instance.end_of_month
    external_rotations = instance.external_rotations
    u_positions = instance.u_positions
    ut_positions = instance.ut_positions

    for i, r in enumerate(residents):
        if r.rank in ["R1", "R2", "R3"] and i not in external_rotations:
            u_count = sum(1 for (ri, _) in u_positions if ri == i)
            ut_pairs = (sum(1 for (ri, _) in ut_positions if ri == i)) // 2
            target = 6 - u_count - ut_pairs
            model.Add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == target
            ).OnlyEnforceIf(enable)
    return enable


# ---------- Distribution constraints ----------


def at_least_one_of_each_type_per_resident(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    end_of_month = instance.end_of_month
    external_rotations = instance.external_rotations

    for i, r in enumerate(residents):
        if i not in external_rotations and r.rank != "R4":
            for k, t in enumerate(state.ShiftType):
                if r.rank != "R1":
                    lits = [
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    ]
                    if lits:
                        model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
                elif t != state.ShiftType.R:
                    lits = [
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    ]
                    if lits:
                        model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
                else:
                    for j, _ in enumerate(days):
                        model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
    return enable


def non_r4_max_two_per_type(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    end_of_month = instance.end_of_month

    for i, r in enumerate(residents):
        if r.rank != "R4":
            for k, _ in enumerate(state.ShiftType):
                model.Add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    )
                    <= 2
                ).OnlyEnforceIf(enable)
    return enable


# ---------- Weekend constraints ----------


def r1_r2_at_least_one_weekend(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    end_of_month = instance.end_of_month
    external_rotations = instance.external_rotations

    for i, r in enumerate(residents):
        if r.rank in ["R1", "R2"] and i not in external_rotations:
            lits = [
                shifts[(i, j, k)]
                for j, d in enumerate(days)
                if d.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            ]
            if lits:
                model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
    return enable


def friday_requires_sunday(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for i, r in enumerate(residents):
        if r.rank != "R4":
            for j, day in enumerate(days):
                if day.day_of_week == "V" and j + 2 < len(days):
                    model.Add(
                        sum(
                            shifts[(i, j, k)]
                            for k, t in enumerate(state.ShiftType)
                            if t != state.ShiftType.R
                        )
                        == sum(
                            shifts[(i, j + 2, k)] for k, _ in enumerate(state.ShiftType)
                        )
                    ).OnlyEnforceIf(enable)
    return enable


def sunday_different_type_than_friday(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week == "V" and j + 2 < len(days):
                for k, _ in enumerate(state.ShiftType):
                    # Not the same type Friday and Sunday
                    model.Add(
                        shifts[(i, j, k)] + shifts[(i, j + 2, k)] <= 1
                    ).OnlyEnforceIf(enable)
    return enable


def block_monday_after_saturday_shift_non_r4(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days

    for i, r in enumerate(residents):
        if r.rank != "R4":
            for j, day in enumerate(days):
                if day.day_of_week == "S" and j + 2 < len(days):
                    model.Add(
                        sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType))
                        + sum(
                            shifts[(i, j + 2, k)] for k, _ in enumerate(state.ShiftType)
                        )
                        <= 1
                    ).OnlyEnforceIf(enable)
    return enable


def block_monday_after_sat_emergency(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    u_positions = instance.u_positions
    days = instance.days

    for i, j in u_positions:
        if days[j].day_of_week == "S" and j < len(days) - 2:
            for k, _ in enumerate(state.ShiftType):
                model.Add(shifts[(i, j + 2, k)] == 0).OnlyEnforceIf(enable)
    return enable


def non_r4_max_one_sunday(model, instance, shifts, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")

    residents = instance.residents
    days = instance.days
    end_of_month = instance.end_of_month

    for i, r in enumerate(residents):
        if r.rank != "R4":
            model.Add(
                sum(
                    shifts[i, j, k]
                    for j, d in enumerate(days)
                    if d.day_of_week == "D" and j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                <= 1
            ).OnlyEnforceIf(enable)
    return enable
