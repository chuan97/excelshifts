"""Assignment pipeline.

This module exposes two entry points:
  - assign_instance(instance, ...): build + solve from an in-memory Instance
  - assign_excel(input_path, sheet_name, ..., save=False): load from Excel and optionally save results back

Validation/diagnostics (unsat cores, cascading relax) will be added later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional

from ortools.sat.cp_model_pb2 import CpSolverStatus
from ortools.sat.python import cp_model

import excelshifts.state as state
from excelshifts.io.excel import copy_excel_file, save_shifts
from excelshifts.io.excel import load_instance as load_instance_from_excel
from excelshifts.model.build import build_model
from excelshifts.model.objective import maximize_total_coverage
from excelshifts.policy import load_enabled_map


@dataclass(slots=True)
class ValidationResult:
    solver_status: CpSolverStatus
    unsat_core: Optional[List[str]]
    wall_time: float


@dataclass(slots=True)
class AssignmentResult:
    matrix: Optional[List[List[str]]]
    objective: Optional[float]
    solver_status: Optional[CpSolverStatus]
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


def _enabled_assumptions(
    enables: Dict[str, Any], enabled_map: Dict[str, bool]
) -> List[Any]:
    # Only include enables for rules that are enabled in the policy
    return [enables[rid] for rid in enables.keys() if enabled_map.get(rid, True)]


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
    policy_path: Optional[str] = None,
    rule_ids: Optional[Iterable[str]] = None,
    time_limit: Optional[float] = None,
    seed: Optional[int] = None,
    num_search_workers: int = 1,
) -> ValidationResult:
    """Build and solve with assumptions to obtain an UNSAT core when infeasible."""
    enabled_map = load_enabled_map(policy_path)

    model, instance, shifts, enables = build_model(
        instance=instance,
        enabled_map=enabled_map,
        rule_ids=list(rule_ids) if rule_ids is not None else None,
    )

    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = float(time_limit)
    if seed is not None:
        solver.parameters.random_seed = int(seed)
    solver.parameters.num_search_workers = int(num_search_workers)

    assumptions = _enabled_assumptions(enables, enabled_map)
    model.ClearAssumptions()
    model.AddAssumptions(assumptions)
    status = solver.Solve(model)

    core: Optional[List[str]] = None
    if status == cp_model.INFEASIBLE:
        core_lits = list(solver.SufficientAssumptionsForInfeasibility())
        core = _core_rule_ids(core_lits, enables)

    return ValidationResult(
        solver_status=status,
        unsat_core=core,
        wall_time=solver.WallTime(),
    )


def assign_instance(
    *,
    instance: state.Instance,
    policy_path: Optional[str] = None,
    rule_ids: Optional[Iterable[str]] = None,
    time_limit: Optional[float] = None,
    seed: Optional[int] = None,
    num_search_workers: int = 1,
    relax: Literal["none", "auto"] = "none",
    relax_limit: int = 1,
) -> AssignmentResult:
    """Solve an assignment for a given Instance, with optional cascading relaxation."""
    base_enabled = load_enabled_map(policy_path)
    current_enabled = dict(base_enabled)

    relaxed: List[str] = []
    first_core: Optional[List[str]] = None

    for attempt in range(0, (relax_limit if relax == "auto" else 0) + 1):
        model, instance, shifts, enables = build_model(
            instance=instance,
            enabled_map=current_enabled,
            rule_ids=list(rule_ids) if rule_ids is not None else None,
        )

        maximize_total_coverage(model, instance, shifts)

        solver = cp_model.CpSolver()
        if time_limit is not None:
            solver.parameters.max_time_in_seconds = float(time_limit)
        if seed is not None:
            solver.parameters.random_seed = int(seed)
        solver.parameters.num_search_workers = int(num_search_workers)

        assumptions = _enabled_assumptions(enables, current_enabled)
        model.ClearAssumptions()
        model.AddAssumptions(assumptions)

        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            matrix = _extract_matrix(solver, instance, shifts)
            obj = solver.ObjectiveValue() if model.Proto().objective else None
            return AssignmentResult(
                matrix=matrix,
                objective=obj,
                solver_status=status,
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )

        # infeasible or unknown
        if relax != "auto" or attempt >= relax_limit:
            return AssignmentResult(
                matrix=None,
                objective=None,
                solver_status=status,
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )

        # Try to obtain an UNSAT core and relax one rule
        # We already solved with assumptions; read the core from this solver
        core_lits = list(solver.SufficientAssumptionsForInfeasibility())
        core_rids = _core_rule_ids(core_lits, enables)
        if first_core is None:
            first_core = core_rids
        # Pick the first enabled rule from the core to relax
        to_disable = next(
            (rid for rid in core_rids if current_enabled.get(rid, True)), None
        )
        if to_disable is None:
            # Fallback: disable the first enabled rule we built
            to_disable = next(
                (rid for rid in enables.keys() if current_enabled.get(rid, True)),
                None,
            )
        if to_disable is None:
            # Nothing to relax
            return AssignmentResult(
                matrix=None,
                objective=None,
                solver_status=status,
                wall_time=solver.WallTime(),
                unsat_core=first_core,
                relaxed_rules=list(relaxed),
            )
        current_enabled[to_disable] = False
        relaxed.append(to_disable)
        # loop and try again
        continue

    # Should not reach here
    return AssignmentResult(
        matrix=None,
        objective=None,
        solver_status=None,
        wall_time=0.0,
        unsat_core=first_core,
        relaxed_rules=list(relaxed),
    )


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
    policy_path: Optional[str] = None,
    rule_ids: Optional[Iterable[str]] = None,
    time_limit: Optional[float] = None,
    seed: Optional[int] = None,
    num_search_workers: int = 1,
    save: bool = False,
    relax: Literal["none", "auto"] = "none",
    relax_limit: int = 1,
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

    result = assign_instance(
        instance=inst,
        policy_path=policy_path,
        rule_ids=rule_ids,
        time_limit=time_limit,
        seed=seed,
        num_search_workers=num_search_workers,
        relax=relax,
        relax_limit=relax_limit,
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
