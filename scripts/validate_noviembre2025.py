from __future__ import annotations

from excelshifts.pipeline import validate_excel

# --- Month-specific configuration ---
INPUT_PATH = "data/Guardias noviembre.xlsx"
SHEET_NAME = "OCTUBRE 2025"

# Coordinates (0-based)
RESIDENTS_START = 4
N_RESIDENTS = 23
DAYS_START = 3
N_DAYS = 30
GRID_ROW_START = 4
GRID_COL_START = 3

# Policy & solver knobs
POLICY_PATH = "policies/custom_noviembre2025_r4presets.yaml"  # adjust if needed
TIME_LIMIT = None  # e.g., 60.0


def main() -> int:
    res = validate_excel(
        input_path=INPUT_PATH,
        sheet_name=SHEET_NAME,
        residents_start=RESIDENTS_START,
        n_residents=N_RESIDENTS,
        days_start=DAYS_START,
        n_days=N_DAYS,
        grid_row_start=GRID_ROW_START,
        grid_col_start=GRID_COL_START,
        policy_path=POLICY_PATH,
        time_limit=TIME_LIMIT,
    )

    print(f"[Validation] status={res.solver_status} time={res.wall_time:.3f}s")

    core = res.unsat_core or []
    print(core)
    if res.solver_status == "INFEASIBLE" and core:
        print("[Validation] Violated rules (subset-minimal):")
        for rid in core:
            print(f"  {rid}")
    else:
        print("[Validation] No rule violations under this policy.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
