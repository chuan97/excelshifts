from __future__ import annotations

from typing import Any, Callable, Dict

from . import library as rules_lib
from .base import RuleSpec

BUILDERS = [
    # ---------- Basic (physical) constraints ----------
    rules_lib.one_shift_per_day,
    rules_lib.restricted_day_off,
    rules_lib.no_R_on_weekends_or_holidays,
    rules_lib.rest_after_any_shift,
    rules_lib.block_around_emergency_u,
    rules_lib.block_around_emergency_ut,
    rules_lib.external_rotation_off,
    # ---------- Coverage constraints ----------
    rules_lib.at_most_one_resident_per_shift_per_day,
    rules_lib.cover_G_or_T_each_day,
    rules_lib.min_assignments_per_day,
    rules_lib.not_same_type_uncovered_both_weekend_days,
    # ---------- Number-of-shifts constraints ----------
    rules_lib.enforce_presets_and_R4_only_presets,
    rules_lib.holiday_assigned_must_work,
    rules_lib.r1_r2_r3_exactly_six_minus_emergencies,
    # ---------- Distribution constraints ----------
    rules_lib.at_least_one_of_each_type_per_resident,
    rules_lib.non_r4_max_two_per_type,
    # ---------- Weekend constraints ----------
    rules_lib.r1_r2_at_least_one_weekend,
    rules_lib.friday_requires_sunday,
    rules_lib.sunday_different_type_than_friday,
    rules_lib.block_monday_after_saturday_shift_non_r4,
    rules_lib.block_monday_after_sat_emergency,
    rules_lib.non_r4_max_one_sunday,
]

assert len({fn.__name__ for fn in BUILDERS}) == len(
    BUILDERS
), "Duplicate builder name in BUILDERS"

# Map stable rule IDs -> builder function from the BUILDERS list
RULES: Dict[str, Callable[[Any, Any, Any, RuleSpec], Any]] = {
    fn.__name__: fn for fn in BUILDERS
}


def list_rule_ids() -> list[str]:
    """Return the stable IDs for all registered rules."""
    return [fn.__name__ for fn in BUILDERS]
