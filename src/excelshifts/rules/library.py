from __future__ import annotations

from typing import Any

import excelshifts.state as state


# Helper to access variables as dict or object
def _get(v: Any, name: str) -> Any:
    return v[name] if isinstance(v, dict) else getattr(v, name)


# ---------- Basic (physical) constraints ----------


def one_shift_per_day(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            model.add_at_most_one(
                shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)
            ).only_enforce_if(enable)
    return enable


def restricted_day_off(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    v_positions = _get(variables, "v_positions")

    for i, j in v_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
    return enable


def no_R_on_weekends_or_holidays(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    p_days = _get(variables, "p_days")

    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week in ["S", "D"] or j in p_days:
                for k, t in enumerate(state.ShiftType):
                    if t == state.ShiftType.R:
                        model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
    return enable


def rest_after_any_shift(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for i, _ in enumerate(residents):
        for j, _ in enumerate(days):
            if j < len(days) - 1:
                for k, _ in enumerate(state.ShiftType):
                    for p, _ in enumerate(state.ShiftType):
                        model.add(shifts[(i, j + 1, p)] == 0).only_enforce_if(
                            [enable, shifts[(i, j, k)]]
                        )
    return enable


def block_around_emergency_u(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    u_positions = _get(variables, "u_positions")
    days = _get(variables, "days")

    for i, j in u_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
            if 0 < j < len(days) - 1:
                model.add(shifts[(i, j + 1, k)] == 0).only_enforce_if(enable)
                model.add(shifts[(i, j - 1, k)] == 0).only_enforce_if(enable)
    return enable


def block_around_emergency_ut(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    ut_positions = _get(variables, "ut_positions")

    for i, j in ut_positions:
        for k, _ in enumerate(state.ShiftType):
            model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
            if j > 0:
                model.add(shifts[(i, j - 1, k)] == 0).only_enforce_if(enable)
    return enable


def external_rotation_off(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    external_rotations = _get(variables, "external_rotations")
    days = _get(variables, "days")

    for i, _ in enumerate(residents):
        if i in external_rotations:
            for j, _ in enumerate(days):
                for k, _ in enumerate(state.ShiftType):
                    model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
    return enable


# ---------- Coverage constraints ----------


def at_most_one_resident_per_shift_per_day(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for j, _ in enumerate(days):
        for k, _ in enumerate(state.ShiftType):
            model.add_at_most_one(
                shifts[(i, j, k)] for i, _ in enumerate(residents)
            ).only_enforce_if(enable)
    return enable


def cover_G_or_T_each_day(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for j, _ in enumerate(days):
        model.add_at_least_one(
            shifts[(i, j, k)]
            for i, _ in enumerate(residents)
            for k, t in enumerate(state.ShiftType)
            if t.name in ["G", "T"]
        ).only_enforce_if(enable)
    return enable


def min_assignments_per_day(model, variables, policy, spec):
    """Implements: 'At most two types of shift can be uncovered each day' using the
    original inequality present in solver.py.
    """
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    p_days = _get(variables, "p_days")

    for j, day in enumerate(days):
        rhs = 1 if (day.day_of_week in ["V", "S", "D"] or j in p_days) else 2
        model.add(
            sum(
                shifts[(i, j, k)]
                for i, _ in enumerate(residents)
                for k, _ in enumerate(state.ShiftType)
            )
            > rhs
        ).only_enforce_if(enable)
    return enable


def not_same_type_uncovered_both_weekend_days(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for j, day in enumerate(days):
        if day.day_of_week == "S" and j < len(days) - 1:
            for k, t in enumerate(state.ShiftType):
                if t.name != "R":
                    model.add_at_least_one(
                        [shifts[(i, j, k)] for i, _ in enumerate(residents)]
                        + [shifts[(i, j + 1, k)] for i, _ in enumerate(residents)]
                    ).only_enforce_if(enable)
    return enable


# ---------- Number-of-shifts constraints ----------


def enforce_presets_and_R4_only_presets(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    presets = _get(variables, "presets")

    for i, r in enumerate(residents):
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                if (i, j, k) in presets:
                    model.add(shifts[(i, j, k)] == 1).only_enforce_if(enable)
                elif r.rank == "R4":
                    model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
    return enable


def holiday_assigned_must_work(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    p_positions = _get(variables, "p_positions")

    for i, j in p_positions:
        model.add(
            sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)) == 1
        ).only_enforce_if(enable)
    return enable


def r3_exactly_six(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")
    external_rotations = _get(variables, "external_rotations")

    for i, r in enumerate(residents):
        if r.rank == "R3" and i not in external_rotations:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6
            ).only_enforce_if(enable)
    return enable


def r2_exactly_six_minus_emergencies(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")
    external_rotations = _get(variables, "external_rotations")
    emergencies = _get(variables, "emergencies")

    for i, r in enumerate(residents):
        if r.rank == "R2" and i not in external_rotations:
            model.add(
                sum(
                    shifts[(i, j, k)]
                    for j, _ in enumerate(days)
                    if j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                == 6 - int(emergencies[i])
            ).only_enforce_if(enable)
    return enable


# ---------- Distribution constraints ----------


def at_least_one_of_each_type_per_resident(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")
    external_rotations = _get(variables, "external_rotations")

    for i, r in enumerate(residents):
        if i not in external_rotations and r.rank != "R4":
            for k, t in enumerate(state.ShiftType):
                if r.rank != "R1":
                    model.add_at_least_one(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    ).only_enforce_if(enable)
                elif t != state.ShiftType.R:
                    model.add_at_least_one(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    ).only_enforce_if(enable)
                else:
                    for j, _ in enumerate(days):
                        model.add(shifts[(i, j, k)] == 0).only_enforce_if(enable)
    return enable


def non_r4_max_two_per_type(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")

    for i, r in enumerate(residents):
        if r.rank != "R4":
            for k, _ in enumerate(state.ShiftType):
                model.add(
                    sum(
                        shifts[(i, j, k)]
                        for j, _ in enumerate(days)
                        if j < end_of_month
                    )
                    <= 2
                ).only_enforce_if(enable)
    return enable


# ---------- Weekend constraints ----------


def r1_r2_at_least_one_weekend(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")
    external_rotations = _get(variables, "external_rotations")

    for i, r in enumerate(residents):
        if r.rank in ["R1", "R2"] and i not in external_rotations:
            model.add_at_least_one(
                shifts[(i, j, k)]
                for j, d in enumerate(days)
                if d.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            ).only_enforce_if(enable)
    return enable


def friday_requires_sunday(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for i, r in enumerate(residents):
        if r.rank != "R4":
            for j, day in enumerate(days):
                if day.day_of_week == "V" and j + 2 < len(days):
                    model.add(
                        sum(
                            shifts[(i, j, k)]
                            for k, t in enumerate(state.ShiftType)
                            if t != state.ShiftType.R
                        )
                        == sum(
                            shifts[(i, j + 2, k)] for k, _ in enumerate(state.ShiftType)
                        )
                    ).only_enforce_if(enable)
    return enable


def sunday_different_type_than_friday(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")

    for i, _ in enumerate(residents):
        for j, day in enumerate(days):
            if day.day_of_week == "V" and j + 2 < len(days):
                for k, _ in enumerate(state.ShiftType):
                    model.add(shifts[(i, j + 2, k)] == 0).only_enforce_if(
                        [enable, shifts[(i, j, k)]]
                    )
    return enable


def block_monday_after_sat_emergency(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    u_positions = _get(variables, "u_positions")
    days = _get(variables, "days")

    for i, j in u_positions:
        if days[j].day_of_week == "S" and j < len(days) - 2:
            for k, _ in enumerate(state.ShiftType):
                model.add(shifts[(i, j + 2, k)] == 0).only_enforce_if(enable)
    return enable


def non_r4_max_one_sunday(model, variables, policy, spec):
    enable = model.NewBoolVar(f"enable_{spec.id}")
    model.add(enable == 1)

    shifts = _get(variables, "shifts")
    residents = _get(variables, "residents")
    days = _get(variables, "days")
    end_of_month = _get(variables, "end_of_month")

    for i, r in enumerate(residents):
        if r.rank != "R4":
            model.add(
                sum(
                    shifts[i, j, k]
                    for j, d in enumerate(days)
                    if d.day_of_week == "D" and j < end_of_month
                    for k, _ in enumerate(state.ShiftType)
                )
                <= 1
            ).only_enforce_if(enable)
    return enable
