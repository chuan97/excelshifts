"""Assignment pipeline.

This module exposes two entry points:
  - assign_instance(instance, ...): build + solve from an in-memory Instance
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


def validate_instance(
    *,
    instance: state.Instance,
    rules: list[BaseRule],
    time_limit: Optional[float] = None,
    seed: Optional[int] = None,
    num_search_workers: int = 1,
) -> ValidationResult:
    """Build and solve with assumptions to obtain an UNSAT core when infeasible."""
    model, shifts, enables = build_model(instance=instance, rules=rules)

    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = float(time_limit)
    if seed is not None:
        solver.parameters.random_seed = int(seed)
    solver.parameters.num_search_workers = int(num_search_workers)

    assumptions = _assumptions(enables, None)
    model.ClearAssumptions()
    model.AddAssumptions(assumptions)
    status = solver.Solve(model)

    core: Optional[List[str]] = None
    if status == cp_model.INFEASIBLE:
        core_lits = list(solver.SufficientAssumptionsForInfeasibility())
        core = _core_rule_ids(core_lits, enables)

    return ValidationResult(
        solver_status=solver.status_name(status),
        unsat_core=core,
        wall_time=solver.WallTime(),
    )


def assign_instance(
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

    result = assign_instance(
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
