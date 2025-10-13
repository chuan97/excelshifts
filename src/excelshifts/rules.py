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

    def new_enable(self, model):  # -> BoolVar
        return model.NewBoolVar(f"enable_{self.rule_id}")

    def targets(self, instance) -> Iterable[tuple[int, Any]]:
        """Yield (index, resident) pairs this rule applies to.

        Only one of the following filters may be specified via params:
        - apply_ranks: iterable of rank strings to include
        - exclude_ranks: iterable of rank strings to exclude
        - include_ids: iterable of resident indices to include
        - exclude_ids: iterable of resident indices to exclude
        If no filter is specified, all residents are yielded.
        Raises ValueError if more than one filter is provided.
        """
        p = self.params or {}
        apply_ranks = set(p.get("apply_ranks") or [])
        exclude_ranks = set(p.get("exclude_ranks") or [])
        include_ids = set(p.get("include_ids") or [])
        exclude_ids = set(p.get("exclude_ids") or [])

        active = [
            name
            for name, s in (
                ("apply_ranks", apply_ranks),
                ("exclude_ranks", exclude_ranks),
                ("include_ids", include_ids),
                ("exclude_ids", exclude_ids),
            )
            if s
        ]
        if len(active) > 1:
            raise ValueError(
                f"Rule {self.rule_id}: specify only one of apply_ranks, exclude_ranks, include_ids, exclude_ids. Got {active}"
            )

        residents = getattr(instance, "residents")

        if apply_ranks:
            for i, r in enumerate(residents):
                if getattr(r, "rank") in apply_ranks:
                    yield i, r
            return

        if exclude_ranks:
            for i, r in enumerate(residents):
                if getattr(r, "rank") not in exclude_ranks:
                    yield i, r
            return

        if include_ids:
            for i, r in enumerate(residents):
                if i in include_ids:
                    yield i, r
            return

        if exclude_ids:
            for i, r in enumerate(residents):
                if i not in exclude_ids:
                    yield i, r
            return

        # No filters -> everyone
        for i, r in enumerate(residents):
            yield i, r


# ---------- Rule classes ----------


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
    PRIORITY = 3

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
    PRIORITY = 3

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


class MaxOneSundayForTargets(BaseRule):
    ID = "max_one_sunday_for_targets"
    PRIORITY = 3

    def apply(self, model, instance, shifts):
        enable = self.new_enable(model)
        days = instance.days
        end_of_month = instance.end_of_month
        for i, _ in self.targets(instance):
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
