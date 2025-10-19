from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, Mapping, Optional

import excelshifts.state as state


@dataclass(frozen=True, slots=True)
class BaseRule:
    """Base class for all scheduling rules.

    Subclasses should override `apply(model, instance, shifts)` to add guarded
    constraints and return a single enable literal (BoolVar). The pipeline will
    pass these enable literals as assumptions to support UNSAT core extraction
    and cascading relaxation.

    Design notes
    ------------
    - `ID` (class var): stable, policy-facing identifier. **Required** for every rule class.
    - `PRIORITY` (class var): larger number means *more* relaxable. The
      instance `priority` defaults to `PRIORITY` when not provided.
    - `params`: free-form mapping for rule-specific tuning (immutable view).
      Filtering of targets is controlled via params (see `targets` method).
    - instance 'id' (optional): if provided, overrides the class-level ID for this instance.
    """

    # Class-level metadata
    ID: ClassVar[str]
    PRIORITY: ClassVar[int]

    # Instance configuration
    priority: Optional[int] = None
    id: Optional[str] = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def apply(self, model, instance, shifts):  # -> BoolVar
        """Add this rule's constraints, guarded by a fresh enable literal.

        Subclasses must implement and **return** the enable literal they used to
        guard their constraints (with `.OnlyEnforceIf(enable)`).
        """
        raise NotImplementedError

    @property
    def rule_id(self) -> str:
        rid_inst = getattr(self, "id", None)
        if isinstance(rid_inst, str) and rid_inst:
            return rid_inst
        rid = getattr(self.__class__, "ID", None)
        if not isinstance(rid, str) or not rid:
            raise ValueError(
                f"Rule class {self.__class__.__name__} must define a non-empty ID"
            )
        return rid

    @property
    def eff_priority(self) -> int:
        return self.priority if self.priority is not None else self.__class__.PRIORITY

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.eff_priority}, rule_id='{self.rule_id}', params={self.params})"

    def new_enable(self, model):  # -> BoolVar
        return model.NewBoolVar(f"enable_{self.rule_id}")

    def targets(self, instance) -> Iterable[tuple[int, Any]]:
        """Yield (index, resident) pairs this rule applies to.

        Allowed filters via params (use **at most two**):
        - include_ranks: iterable of rank strings to include
        - exclude_ranks: iterable of rank strings to exclude
        - include_names: iterable of resident names to include
        - exclude_names: iterable of resident names to exclude

        Valid usages:
        - Any single filter alone, or none (all residents)
        - Exactly these two-filter combinations:
          * include_ranks + exclude_names  (start from ranks, then subtract names)
          * exclude_ranks + include_names  (exclude ranks, but whitelist names)

        Residents in external rotations are automatically excluded from targets.
        """
        p = self.params or {}
        include_ranks = set(p.get("include_ranks") or [])
        exclude_ranks = set(p.get("exclude_ranks") or [])
        include_names = set(map(str, p.get("include_names") or []))
        exclude_names = set(map(str, p.get("exclude_names") or []))

        active = [
            name
            for name, s in (
                ("include_ranks", include_ranks),
                ("exclude_ranks", exclude_ranks),
                ("include_names", include_names),
                ("exclude_names", exclude_names),
            )
            if s
        ]

        if len(active) > 2:
            raise ValueError(
                f"Rule {self.rule_id}: at most two filters allowed. Got {active}"
            )
        if len(active) == 2 and set(active) not in (
            {"include_ranks", "exclude_names"},
            {"exclude_ranks", "include_names"},
        ):
            raise ValueError(
                f"Rule {self.rule_id}: invalid filter combination {active}. "
                "Allowed pairs: include_ranks+exclude_names, exclude_ranks+include_names."
            )

        residents = getattr(instance, "residents")
        external = set(getattr(instance, "external_rotations", ()))

        # Build predicate per the active filters
        if not active:

            def ok(i, r):
                return True

        elif active == ["include_ranks"] or active == ["exclude_ranks"]:
            if include_ranks:

                def ok(i, r):
                    return getattr(r, "rank") in include_ranks

            else:

                def ok(i, r):
                    return getattr(r, "rank") not in exclude_ranks

        elif active == ["include_names"] or active == ["exclude_names"]:
            if include_names:

                def ok(i, r):
                    return getattr(r, "name", None) in include_names

            else:

                def ok(i, r):
                    return getattr(r, "name", None) not in exclude_names

        elif set(active) == {"include_ranks", "exclude_names"}:

            def ok(i, r):
                return (
                    getattr(r, "rank") in include_ranks
                    and getattr(r, "name", None) not in exclude_names
                )

        else:  # set(active) == {"exclude_ranks", "include_names"}

            def ok(i, r):
                # Allowlisted names are included even if their rank is excluded
                return (getattr(r, "rank") not in exclude_ranks) or (
                    getattr(r, "name", None) in include_names
                )

        # Yield after excluding external rotations
        for i, r in enumerate(residents):
            if i in external:
                continue
            if ok(i, r):
                yield i, r


# ---------- Physical constraints ----------


class OneShiftPerDay(BaseRule):
    ID = "one_shift_per_day"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        residents = instance.residents
        days = instance.days
        for i, _ in enumerate(residents):
            for j, _ in enumerate(days):
                lits = [shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)]
                if lits:
                    model.Add(sum(lits) <= 1).OnlyEnforceIf(enable)
        return enable


class RestrictedDayOff(BaseRule):
    ID = "restricted_day_off"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        v_positions = instance.v_positions
        for i, j in v_positions:
            for k, _ in enumerate(state.ShiftType):
                model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
        return enable


class NoROnWeekendsOrHolidays(BaseRule):
    ID = "no_R_on_weekends_or_holidays"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
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


class RestAfterAnyShift(BaseRule):
    ID = "rest_after_any_shift"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        residents = instance.residents
        days = instance.days
        for i, _ in enumerate(residents):
            for j, _ in enumerate(days):
                if j < len(days) - 1:
                    model.Add(
                        sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType))
                        + sum(
                            shifts[(i, j + 1, k)] for k, _ in enumerate(state.ShiftType)
                        )
                        <= 1
                    ).OnlyEnforceIf(enable)
        return enable


class BlockAroundEmergencyU(BaseRule):
    ID = "block_around_emergency_u"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        u_positions = instance.u_positions
        days = instance.days
        for i, j in u_positions:
            for k, _ in enumerate(state.ShiftType):
                model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
                if 0 < j < len(days) - 1:
                    model.Add(shifts[(i, j + 1, k)] == 0).OnlyEnforceIf(enable)
                    model.Add(shifts[(i, j - 1, k)] == 0).OnlyEnforceIf(enable)
        return enable


class BlockAroundEmergencyUT(BaseRule):
    ID = "block_around_emergency_ut"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        ut_positions = instance.ut_positions
        for i, j in ut_positions:
            for k, _ in enumerate(state.ShiftType):
                model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
                if j > 0:
                    model.Add(shifts[(i, j - 1, k)] == 0).OnlyEnforceIf(enable)
        return enable


class ExternalRotationOff(BaseRule):
    ID = "external_rotation_off"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        residents = instance.residents
        days = instance.days
        external = instance.external_rotations
        for i, _ in enumerate(residents):
            if i in external:
                for j, _ in enumerate(days):
                    for k, _ in enumerate(state.ShiftType):
                        model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
        return enable


# ---------- Coverage constraints ----------


class AtMostOneResidentPerShiftPerDay(BaseRule):
    ID = "at_most_one_resident_per_shift_per_day"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        residents = instance.residents
        days = instance.days
        for j, _ in enumerate(days):
            for k, _ in enumerate(state.ShiftType):
                lits = [shifts[(i, j, k)] for i, _ in enumerate(residents)]
                if lits:
                    model.Add(sum(lits) <= 1).OnlyEnforceIf(enable)
        return enable


class CoverGorTEachDay(BaseRule):
    ID = "cover_G_or_T_each_day"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
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


class SeniorGorTRequiresOtherCoverage(BaseRule):
    """
    If a resident whose rank is in `params['ranks']` is assigned G or T
    on day j, require that some other resident covers the complementary T or G on day j.
    """

    ID = "senior_G_or_T_requires_other_coverage"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        residents = instance.residents
        days = instance.days

        k_G = state.ShiftType.G.value
        k_T = state.ShiftType.T.value

        ranks_param = self.params.get("ranks")
        if not isinstance(ranks_param, (list, tuple)) or not ranks_param:
            raise ValueError(
                "senior_G_or_T_requires_other_coverage requires param 'ranks' as a non-empty list of rank strings"
            )
        senior_ranks = {str(x) for x in ranks_param}

        for i, r in enumerate(residents):
            if getattr(r, "rank", None) in senior_ranks:
                for j, _ in enumerate(days):
                    # If i does G on day j, someone else must do T on day j
                    lits_T_others = [
                        shifts[(h, j, k_T)] for h, _ in enumerate(residents) if h != i
                    ]
                    if lits_T_others:
                        model.Add(sum(lits_T_others) >= 1).OnlyEnforceIf(
                            [enable, shifts[(i, j, k_G)]]
                        )

                    # If i does T on day j, someone else must do G on day j
                    lits_G_others = [
                        shifts[(h, j, k_G)] for h, _ in enumerate(residents) if h != i
                    ]
                    if lits_G_others:
                        model.Add(sum(lits_G_others) >= 1).OnlyEnforceIf(
                            [enable, shifts[(i, j, k_T)]]
                        )

        return enable


class MinAssignmentsPerDay(BaseRule):
    ID = "min_assignments_per_day"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
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


class NotSameTypeUncoveredBothWeekendDays(BaseRule):
    ID = "not_same_type_uncovered_both_weekend_days"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
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


class EnforcePresets(BaseRule):
    ID = "enforce_presets"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        # Enforce given presets for everyone (exactly those cells must be 1)
        for i, j, k in instance.presets:
            model.Add(shifts[(i, j, k)] == 1).OnlyEnforceIf(enable)
        return enable


class OnlyPresetsForTargets(BaseRule):
    ID = "only_presets_for_targets"
    PRIORITY = 2  # softer than enforcing presets; relaxable if needed

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        target_ids = {i for i, _ in self.targets(instance)}
        if not target_ids:
            return enable
        # For targeted residents, forbid any non-preset shifts ("only presets")
        for i in target_ids:
            for j, _ in enumerate(days):
                for k, _ in enumerate(state.ShiftType):
                    if (i, j, k) not in instance.presets:
                        model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
        return enable


class HolidayAssignedMustWork(BaseRule):
    ID = "holiday_assigned_must_work"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        p_positions = instance.p_positions
        for i, j in p_positions:
            model.Add(
                sum(shifts[(i, j, k)] for k, _ in enumerate(state.ShiftType)) == 1
            ).OnlyEnforceIf(enable)
        return enable


class TotalNumberOfShifts(BaseRule):
    ID = "total_number_of_shifts"
    PRIORITY = 2

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month

        params = dict(self.params or {})
        if "total" not in params:
            raise ValueError("total_number_of_shifts requires integer param 'total'")
        try:
            base_total = int(params["total"])
        except Exception as e:
            raise ValueError("total_number_of_shifts 'total' must be an int") from e

        # compute targets first
        target_ids = [i for i, _ in self.targets(instance)]
        if not target_ids:
            return enable

        # Always adjust: U counts as 1, every two UT count as 1 (pairs)
        u_count = {i: 0 for i in target_ids}
        ut_count = {i: 0 for i in target_ids}
        for ri, _ in instance.u_positions:
            if ri in u_count:
                u_count[ri] += 1
        for ri, _ in instance.ut_positions:
            if ri in ut_count:
                ut_count[ri] += 1

        for i in target_ids:
            rhs = base_total - u_count.get(i, 0) - (ut_count.get(i, 0) // 2)
            if rhs < 0:
                rhs = 0

            lits = [
                shifts[(i, j, k)]
                for j, _ in enumerate(days)
                if j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            ]

            model.Add(sum(lits) == rhs).OnlyEnforceIf(enable)

        return enable


# ---------- Distribution constraints ----------


class TargetsDoAtLeastOfType(BaseRule):
    ID = "targets_do_at_least_of_type"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month

        # required param: list of shift type names, e.g., ["R", "G", "T"]
        types_param = self.params.get("types")
        if not isinstance(types_param, (list, tuple)) or not types_param:
            raise ValueError(
                "targets_do_at_least_of_type requires a non-empty list param 'types'"
            )
        wanted = {str(x).upper() for x in types_param}
        known = {t.name for t in state.ShiftType}
        unknown = wanted - known
        if unknown:
            raise ValueError(
                f"Unknown shift types in 'types': {sorted(unknown)}; known={sorted(known)}"
            )
        k_list = [k for k, t in enumerate(state.ShiftType) if t.name in wanted]

        target_ids = [i for i, _ in self.targets(instance)]
        for i in target_ids:
            for k in k_list:
                lits = [
                    shifts[(i, j, k)] for j, _ in enumerate(days) if j < end_of_month
                ]
                if lits:
                    model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
        return enable


class TargetsDoNotDoType(BaseRule):
    ID = "targets_do_not_do_type"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days

        # required param: list of shift type names to forbid entirely
        types_param = self.params.get("types")
        if not isinstance(types_param, (list, tuple)) or not types_param:
            raise ValueError(
                "targets_do_not_do_type requires a non-empty list param 'types'"
            )
        wanted = {str(x).upper() for x in types_param}
        known = {t.name for t in state.ShiftType}
        unknown = wanted - known
        if unknown:
            raise ValueError(
                f"Unknown shift types in 'types': {sorted(unknown)}; known={sorted(known)}"
            )
        k_list = [k for k, t in enumerate(state.ShiftType) if t.name in wanted]

        target_ids = [i for i, _ in self.targets(instance)]
        for i in target_ids:
            for j, _ in enumerate(days):
                for k in k_list:
                    model.Add(shifts[(i, j, k)] == 0).OnlyEnforceIf(enable)
        return enable


class MaxTwoPerTypeForTargets(BaseRule):
    ID = "max_two_per_type_for_targets"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month
        for i, _ in self.targets(instance):
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


class AtLeastOneWeekendForTargets(BaseRule):
    ID = "at_least_one_weekend_for_targets"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month
        for i, _ in self.targets(instance):
            lits = [
                shifts[(i, j, k)]
                for j, d in enumerate(days)
                if d.day_of_week in ["S", "D"] and j < end_of_month
                for k, _ in enumerate(state.ShiftType)
            ]
            if lits:
                model.Add(sum(lits) >= 1).OnlyEnforceIf(enable)
        return enable


class FridayRequiresSunday(BaseRule):
    ID = "friday_requires_sunday"
    PRIORITY = 1

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        for i, _ in self.targets(instance):
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


class SundayDifferentTypeThanFriday(BaseRule):
    ID = "sunday_different_type_than_friday"
    PRIORITY = 2

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        for i, _ in self.targets(instance):
            for j, day in enumerate(days):
                if day.day_of_week == "V" and j + 2 < len(days):
                    for k, _ in enumerate(state.ShiftType):
                        model.Add(
                            shifts[(i, j, k)] + shifts[(i, j + 2, k)] <= 1
                        ).OnlyEnforceIf(enable)
        return enable


class BlockMondayAfterSaturdayShiftTargets(BaseRule):
    ID = "block_monday_after_saturday_shift_targets"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        for i, _ in self.targets(instance):
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


class BlockMondayAfterSatEmergency(BaseRule):
    ID = "block_monday_after_sat_emergency"
    PRIORITY = 4

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        u_positions = instance.u_positions
        days = instance.days
        target_ids = {i for i, _ in self.targets(instance)}
        for i, j in u_positions:
            if i in target_ids and days[j].day_of_week == "S" and j < len(days) - 2:
                for k, _ in enumerate(state.ShiftType):
                    model.Add(shifts[(i, j + 2, k)] == 0).OnlyEnforceIf(enable)
        return enable


class MaxWeekendShiftsForTargets(BaseRule):
    ID = "max_weekend_shifts_for_targets"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days

        # required param: maximum number of weekend shifts per targeted resident
        try:
            max_weekend = int(self.params["max"])
        except Exception as e:
            raise ValueError(
                "max_weekend_shifts_for_targets requires integer param 'max'"
            ) from e
        if max_weekend < 0:
            raise ValueError("'max' must be a non-negative integer")

        weekend_js = [j for j, d in enumerate(days) if d.day_of_week in ["S", "D"]]

        # Constraints per targeted resident
        for i, _ in self.targets(instance):
            lits = [
                shifts[(i, j, k)]
                for j in weekend_js
                for k, _ in enumerate(state.ShiftType)
            ]

            # Count emergency U / UT that fall on weekends for resident i
            u_extra = sum(
                1 for ri, dj in instance.u_positions if ri == i and dj in weekend_js
            )
            ut_extra = sum(
                1 for ri, dj in instance.ut_positions if ri == i and dj in weekend_js
            )

            if lits or u_extra or ut_extra:
                model.Add(sum(lits) + u_extra + ut_extra <= max_weekend).OnlyEnforceIf(
                    enable
                )

        return enable


# New rule: WeekendBalanceForTargets
class WeekendBalanceForTargets(BaseRule):
    ID = "weekend_balance_for_targets"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month

        # Collect Saturday and Sunday indices in the planning horizon, strictly before end_of_month
        sat_js = [
            j for j, d in enumerate(days) if j < end_of_month and d.day_of_week == "S"
        ]
        sun_js = [
            j for j, d in enumerate(days) if j < end_of_month and d.day_of_week == "D"
        ]

        for i, _ in self.targets(instance):
            sat_lits = [
                shifts[(i, j, k)] for j in sat_js for k, _ in enumerate(state.ShiftType)
            ]
            sun_lits = [
                shifts[(i, j, k)] for j in sun_js for k, _ in enumerate(state.ShiftType)
            ]

            # |#Sat - #Sun| <= 1  <=>  (#Sat - #Sun <= 1) and (#Sun - #Sat <= 1)
            model.Add(sum(sat_lits) - sum(sun_lits) <= 1).OnlyEnforceIf(enable)
            model.Add(sum(sun_lits) - sum(sat_lits) <= 1).OnlyEnforceIf(enable)

        return enable


# ------------- Quality of life constraints ------------------


class NoMShiftsInNDays(BaseRule):
    ID = "no_m_shifts_in_n_days"
    PRIORITY = 0

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days

        # Enforce: in any `n_days` window, total counted shifts (incl. R) + U-days < `m_shifts`
        try:
            m_shifts = self.params["m_shifts"]
            n_days = self.params["n_days"]
        except Exception as e:
            raise ValueError(
                "no_m_shifts_in_n_days requires integer params 'm_shifts' and 'n_days'"
            ) from e
        if m_shifts <= 0 or n_days <= 0:
            raise ValueError("'m_shifts' and 'n_days' must be positive integers")
        if n_days > len(days):
            raise ValueError("'n_days' is larger the number of days in the month")

        for i, _ in self.targets(instance):
            for j in range(0, max(0, len(days) - n_days + 1)):
                lits = [
                    shifts[(i, d, k)]
                    for d in range(j, j + n_days)
                    for k, _ in enumerate(state.ShiftType)
                ]

                u_extra = sum(
                    1
                    for ri, dj in instance.u_positions
                    if ri == i and j <= dj < j + n_days
                )

                model.Add(sum(lits) + u_extra < m_shifts).OnlyEnforceIf(enable)

        return enable


# ---------- Auto registry & helpers ----------


def _all_rule_classes() -> list[type[BaseRule]]:
    # Recursively collect all subclasses so we don't miss indirect ones.
    out: list[type[BaseRule]] = []
    q = list(BaseRule.__subclasses__())
    seen: set[type[BaseRule]] = set()
    while q:
        cls = q.pop()
        if cls in seen:
            continue
        seen.add(cls)
        out.append(cls)
        q.extend(cls.__subclasses__())
    return out


# Map stable rule IDs -> rule classes
RULES_BY_ID: dict[str, type[BaseRule]] = {cls.ID: cls for cls in _all_rule_classes()}


def get_rule_class(rule_id: str) -> type[BaseRule]:
    try:
        return RULES_BY_ID[rule_id]
    except KeyError as e:
        known = ", ".join(sorted(RULES_BY_ID))
        raise KeyError(f"Unknown rule id '{rule_id}'. Known: {known}") from e


def apply_rules(
    model: Any,
    instance: Any,
    shifts: Any,
    rules: Iterable[Any],
) -> dict[str, Any]:
    """Apply instantiated rule objects to the model.

    Each rule must implement `.apply(model, instance, shifts)` and return its
    enable literal. We do not force `enable == 1`; callers may pass these
    literals as solver assumptions to obtain UNSAT cores.
    """
    enables: dict[str, Any] = {}
    for rule in rules:
        enable = rule.apply(model, instance, shifts)
        enables[rule.rule_id] = enable
    return enables
