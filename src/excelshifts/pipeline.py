"""Assignment pipeline.

This module exposes two entry points:
  - assign(instance, ...): build + solve from an in-memory Instance
  - assign_excel(input_path, sheet_name, ..., save=False): load from Excel and optionally save results back

Validation/diagnostics (unsat cores, cascading relax) will be added later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ortools.sat.python import cp_model

import excelshifts.state as state
from excelshifts.io.excel import copy_excel_file, save_shifts
from excelshifts.io.excel import load_instance as load_instance_from_excel
from excelshifts.io.policy import load_rules
from excelshifts.model.build import build_model
from excelshifts.model.constraints import BaseRule
from excelshifts.model.objective import maximize_total_coverage


@dataclass(slots=True)
class ValidationResult:
    solver_status: str
    unsat_core: Optional[List[str]]
    wall_time: float


@dataclass(slots=True)
class AssignmentResult:
    matrix: Optional[List[List[str]]]
    objective: Optional[float]
    solver_status: str
    wall_time: float
    unsat_core: Optional[List[str]] = None
    relaxed_rules: List[str] = field(default_factory=list)


def _extract_matrix(
    solver: cp_model.CpSolver,
    instance: state.Instance,
    shifts: Dict[tuple[int, int, int], Any],
) -> List[List[str]]:
    matrix: List[List[str]] = []
    for i, _ in enumerate(instance.residents):
        row: List[str] = []
        for j, _ in enumerate(instance.days):
            code = ""
            for k, t in enumerate(state.ShiftType):
                if solver.Value(shifts[(i, j, k)]):
                    code = t.name
                    break
            row.append(code)
        matrix.append(row)
    return matrix


def _assumptions(
    enables: Dict[str, Any], active_ids: Optional[Iterable[str]]
) -> List[Any]:
    active: Optional[set[str]] = set(active_ids) if active_ids is not None else None
    return [enables[rid] for rid in enables.keys() if active is None or rid in active]


def _core_rule_ids(core_lits: List[Any], enables: Dict[str, Any]) -> List[str]:
    # Map core literals back to rule ids using identity or, as a fallback, Name()
    id_map = {id(var): rid for rid, var in enables.items()}
    rid_list: List[str] = []
    for lit in core_lits:
        rid = id_map.get(id(lit))
        if rid is None:
            try:
                lit_name = lit.Name()  # type: ignore[attr-defined]
            except Exception:
                lit_name = None
            if lit_name is not None:
                for r, v in enables.items():
                    try:
                        if v.Name() == lit_name:  # type: ignore[attr-defined]
                            rid = r
                            break
                    except Exception:
                        pass
        if rid is not None:
            rid_list.append(rid)
    # Keep order and uniqueness
    seen = set()
    out: List[str] = []
    for r in rid_list:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _fix_presets(
    model: cp_model.CpModel,
    shifts: Dict[tuple[int, int, int], Any],
    presets: tuple[tuple[int, int, int]],
) -> None:
    """Force exact assignments for preset triplets (i, j, k).

    For each (i, j, k*), set shifts[(i, j, k*)] == 1 and all other k != k* at (i, j) to 0.
    """
    for i, j, k_star in presets:
        # 1) the chosen one is True
        model.Add(shifts[(i, j, k_star)] == 1)
        # 2) all others are False
        for k, _ in enumerate(state.ShiftType):
            if k != k_star:
                model.Add(shifts[(i, j, k)] == 0)


def _shrink_core_to_mus(
    *,
    model: cp_model.CpModel,
    enables: Dict[str, Any],
    core_ids: List[str],
    time_limit: Optional[float],
) -> List[str]:
    # Greedy deletion-based MUS: try removing each assumption and keep it removed if infeasibility persists

    # Work on a copy of core_ids to preserve given order
    mus = list(core_ids)

    for rid in core_ids:
        if rid not in mus:
            continue
        # Temporarily drop this assumption
        trial = [enables[x] for x in mus if x != rid]

        solver = cp_model.CpSolver()
        if time_limit is not None:
            solver.parameters.max_time_in_seconds = float(time_limit)
        model.ClearAssumptions()
        model.AddAssumptions(trial)
        status = solver.Solve(model)
        if status == cp_model.INFEASIBLE:
            # still UNSAT without rid => rid not necessary
            mus.remove(rid)
        # else: necessary => keep rid in mus

    return mus


def validate(
    *,
    instance: state.Instance,
    rules: list[BaseRule],
    time_limit: Optional[float] = None,
) -> ValidationResult:
    """Build and solve with assumptions to obtain an UNSAT core when infeasible."""
    model, shifts, enables = build_model(instance=instance, rules=rules)
    print(instance.presets)
    print(instance.residents)
    print(rules)
    # Apply presets contained in the instance (single source of truth)
    presets = getattr(instance, "presets", None)
    if presets is not None:
        _fix_presets(model, shifts, presets)

    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = float(time_limit)

    assumptions = _assumptions(enables, None)
    model.ClearAssumptions()
    model.AddAssumptions(assumptions)
    status = solver.Solve(model)
    print(solver.status_name(status))
    core: Optional[list[str]] = None
    if status == cp_model.INFEASIBLE:
        core_lits_idx = list(solver.SufficientAssumptionsForInfeasibility())
        core_lits = [model.get_bool_var_from_proto_index(idx) for idx in core_lits_idx]
        core_rids = _core_rule_ids(core_lits, enables)
        # Greedily shrink to a subset-minimal core (MUS)
        core = _shrink_core_to_mus(
            model=model,
            enables=enables,
            core_ids=core_rids,
            time_limit=time_limit,
        )

    return ValidationResult(
        solver_status=solver.status_name(status),
        unsat_core=core,
        wall_time=solver.WallTime(),
    )


def assign(
    *,
    instance: state.Instance,
    rules: list[BaseRule],
    time_limit: Optional[float] = None,
) -> AssignmentResult:
    """Solve an assignment for a given Instance, always relaxing constraints as needed."""
    active_ids: Optional[set[str]] = None

    # Map rule_id -> PRIORITY from provided rule instances
    def _rid(r: BaseRule) -> str:
        return (
            getattr(r, "rule_id", None)
            or getattr(r, "ID", None)
            or r.__class__.__name__
        )

    rule_priority: dict[str, int] = {_rid(r): int(r.eff_priority) for r in rules}
    relaxed: List[str] = []
    first_core: Optional[List[str]] = None

    attempt = 0
    while True:
        model, shifts, enables = build_model(
            instance=instance,
            rules=rules,
        )

        if active_ids is None:
            active_ids = set(enables.keys())

        maximize_total_coverage(model, instance, shifts)

        solver = cp_model.CpSolver()
        if time_limit is not None:
            solver.parameters.max_time_in_seconds = float(time_limit)

        assumptions = _assumptions(enables, active_ids)
        model.ClearAssumptions()
        model.AddAssumptions(assumptions)

        status = solver.Solve(model)
        print(f"[Assignment] Attempt {attempt}, result: {solver.status_name(status)}")

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # --- Trim pass: try to re-enable disabled rules while keeping feasibility ---
            if relaxed:
                # Sort relaxed rules by ascending priority (more important first),
                # preserving original order within the same priority tier.
                relaxed_sorted = sorted(
                    relaxed,
                    key=lambda rid: (rule_priority.get(rid, 0), relaxed.index(rid)),
                )

                for rid in relaxed_sorted:
                    # Tentatively re-enable and test feasibility
                    active_ids.add(rid)

                    model_t, shifts_t, enables_t = build_model(
                        instance=instance,
                        rules=rules,
                    )
                    maximize_total_coverage(model_t, instance, shifts_t)

                    solver_t = cp_model.CpSolver()
                    if time_limit is not None:
                        solver_t.parameters.max_time_in_seconds = float(time_limit)

                    assumptions_t = _assumptions(enables_t, active_ids)
                    model_t.ClearAssumptions()
                    model_t.AddAssumptions(assumptions_t)

                    status_t = solver_t.Solve(model_t)
                    print(
                        f"[Assignment] Attempting reenable, result: {solver.status_name(status_t)}"
                    )
                    if status_t not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                        # Not feasible -> keep it disabled
                        active_ids.remove(rid)
                        continue
                    # Feasible -> keep enabled and continue trying to recover more rules

            # Final solve with trimmed active_ids to obtain matrix/objective and final relaxed set
            model_f, shifts_f, enables_f = build_model(
                instance=instance,
                rules=rules,
            )
            maximize_total_coverage(model_f, instance, shifts_f)

            solver_f = cp_model.CpSolver()
            if time_limit is not None:
                solver_f.parameters.max_time_in_seconds = float(time_limit)

            assumptions_f = _assumptions(enables_f, active_ids)
            model_f.ClearAssumptions()
            model_f.AddAssumptions(assumptions_f)
            status_f = solver_f.Solve(model_f)

            if status_f not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                # Should not happen; fallback to original feasible result without trimming
                matrix = _extract_matrix(solver, instance, shifts)
                obj = solver.ObjectiveValue() if model.Proto().objective else None
                return AssignmentResult(
                    matrix=matrix,
                    objective=obj,
                    solver_status=solver.status_name(status),
                    wall_time=solver.WallTime(),
                    unsat_core=first_core,
                    relaxed_rules=list(relaxed),
                )

            # Success: return trimmed result
            matrix = _extract_matrix(solver_f, instance, shifts_f)
            obj = solver_f.ObjectiveValue() if model_f.Proto().objective else None
            final_relaxed = [rid for rid in enables_f.keys() if rid not in active_ids]
            return AssignmentResult(
                matrix=matrix,
                objective=obj,
                solver_status=solver_f.status_name(status_f),
                wall_time=solver_f.WallTime(),
                unsat_core=first_core,
                relaxed_rules=final_relaxed,
            )

        if status != cp_model.INFEASIBLE:
            return AssignmentResult(
                matrix=None,
                objective=None,
                solver_status=solver.status_name(status),
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )

        core_lits_idx = list(solver.SufficientAssumptionsForInfeasibility())
        core_lits = [model.get_bool_var_from_proto_index(idx) for idx in core_lits_idx]
        core_rids = _core_rule_ids(core_lits, enables)

        if first_core is None:
            first_core = core_rids
        # Priority-aware relaxation: disable highest-priority enabled rule from the core
        enabled_core = [rid for rid in core_rids if rid in active_ids]
        if not enabled_core:
            return AssignmentResult(
                matrix=None,
                objective=None,
                solver_status=solver.status_name(status),
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )
        max_prio = max(rule_priority.get(rid, 0) for rid in enabled_core)
        candidates = [
            rid
            for rid in core_rids
            if rid in enabled_core and rule_priority.get(rid, 0) == max_prio
        ]
        to_disable = candidates[0] if candidates else None
        if to_disable is None:
            return AssignmentResult(
                matrix=None,
                objective=None,
                solver_status=solver.status_name(status),
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )

        active_ids.remove(to_disable)
        relaxed.append(to_disable)
        attempt += 1


def assign_excel(
    *,
    input_path: str,
    sheet_name: str,
    residents_start: int,
    n_residents: int,
    days_start: int,
    n_days: int,
    grid_row_start: int,
    grid_col_start: int,
    policy_path: str,
    time_limit: Optional[float] = None,
    save: bool = False,
) -> AssignmentResult:
    """Load inputs from Excel, solve, and optionally write the result back to the sheet."""
    inst = load_instance_from_excel(
        input_path,
        sheet_name,
        residents_start=residents_start,
        n_residents=n_residents,
        days_start=days_start,
        n_days=n_days,
        grid_row_start=grid_row_start,
        grid_col_start=grid_col_start,
    )

    rules = load_rules(policy_path)

    result = assign(
        instance=inst,
        rules=rules,
        time_limit=time_limit,
    )

    if save and result.matrix is not None:
        output_path = copy_excel_file(input_path, "_solved")
        save_shifts(
            file_path=output_path,
            sheet_name=sheet_name,
            shift_matrix=result.matrix,
            row_start=grid_row_start,
            col_start=grid_col_start,
        )

    return result


def validate_excel(
    *,
    input_path: str,
    sheet_name: str,
    residents_start: int,
    n_residents: int,
    days_start: int,
    n_days: int,
    grid_row_start: int,
    grid_col_start: int,
    policy_path: str,
    time_limit: Optional[float] = None,
) -> ValidationResult:
    """Load inputs from Excel and validate against the policy rules.

    Presets (partial or full assignments) must be embedded in the Instance by the Excel loader.
    """
    inst = load_instance_from_excel(
        input_path,
        sheet_name,
        residents_start=residents_start,
        n_residents=n_residents,
        days_start=days_start,
        n_days=n_days,
        grid_row_start=grid_row_start,
        grid_col_start=grid_col_start,
    )

    rules = load_rules(policy_path)

    return validate(
        instance=inst,
        rules=rules,
        time_limit=time_limit,
    )
