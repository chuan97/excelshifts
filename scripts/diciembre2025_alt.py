from __future__ import annotations

from excelshifts.pipeline import assign_excel

# --- Month-specific configuration ---
INPUT_PATH = "data/Guardias diciembre.xlsx"
SHEET_NAME = "DICIEMBRE 2025"

# Coordinates (0-based)
RESIDENTS_START = 4
N_RESIDENTS = 22
DAYS_START = 3
N_DAYS = 31
GRID_ROW_START = 4
GRID_COL_START = 3
P_DAYS = [
    8,
    19,
    26,
]

# Policy & solver knobs
POLICY_PATH = "policies/custom_diciembre2025.yaml"
TIME_LIMIT = None  # e.g., 60.0

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
        p_days=P_DAYS,
        policy_path=POLICY_PATH,
        time_limit=TIME_LIMIT,
        save=SAVE,
    )

    print(
        f"[Result] status={res.solver_status} objective={res.objective} time={res.wall_time:.3f}s"
    )

    relaxed = res.relaxed_rules or []

    if relaxed:
        print("[Result] Relaxed rules:")
        for rid in relaxed:
            print(f"  {rid}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
