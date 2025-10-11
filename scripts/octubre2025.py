from __future__ import annotations

from typing import Literal

from excelshifts.pipeline import assign_excel

RelaxMode = Literal["none", "auto"]

# --- Month-specific configuration ---
INPUT_PATH = "data/Guardias octubre.xlsx"
SHEET_NAME = "OCTUBRE 2025"

# Coordinates (0-based)
RESIDENTS_START = 4
N_RESIDENTS = 22
DAYS_START = 3
N_DAYS = 33
GRID_ROW_START = 4
GRID_COL_START = 3

# Policy & solver knobs
POLICY_PATH = "policies/all_off.yaml"  # adjust if needed
TIME_LIMIT = None  # e.g., 60.0
SEED = None  # e.g., 123
WORKERS = 1  # keep 1 for determinism
RELAX: RelaxMode = "auto"  # "none" or "auto"
RELAX_LIMIT = 100  # max number of rules to relax when RELAX=="auto"
SAVE = True  # write to a copy: *_solved.xlsx


def main() -> int:
    res = assign_excel(
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
        seed=SEED,
        num_search_workers=WORKERS,
        relax=RELAX,
        relax_limit=RELAX_LIMIT,
        save=SAVE,
    )

    print(
        f"status={res.solver_status} objective={res.objective} time={res.wall_time:.3f}s"
    )
    if getattr(res, "relaxed_rules", None) and res.relaxed_rules:
        print("relaxed=[" + ", ".join(res.relaxed_rules) + "]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
