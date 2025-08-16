import excelshifts.excel_io as excel
from excelshifts.solver import solve_shifts

f_path = "data/Guardias mayo.xlsx"
sheet_name = "Mayo 2025"

row_start = 4
col_start = 3
n_residents = 21
n_days = 32

residents = excel.load_residents(f_path, sheet_name, row_start, n_residents)
days = excel.load_days(f_path, sheet_name, col_start, n_days)
v_positions = excel.load_restrictions(
    f_path,
    sheet_name,
    ["V", "B", "Mo", "Cu", "Co", "Con"],
    row_start,
    col_start,
    n_residents,
    n_days,
)
u_positions = excel.load_restrictions(
    f_path, sheet_name, ["U"], row_start, col_start, n_residents, n_days
)
ut_positions = excel.load_restrictions(
    f_path, sheet_name, ["UT"], row_start, col_start, n_residents, n_days
)
p_positions = excel.load_restrictions(
    f_path, sheet_name, ["P"], row_start, col_start, n_residents, n_days
)
external_rotations = excel.load_external_rotations(
    f_path, sheet_name, row_start, col_start, n_residents, n_days
)
totals = excel.load_totals(f_path, "Global", 3, 2, n_residents)
preset_shifts = excel.load_preset_shifts(
    f_path, sheet_name, row_start, col_start, n_residents, n_days
)

shifts_matrix = solve_shifts(
    residents,
    days,
    v_positions,
    u_positions,
    ut_positions,
    p_positions,
    external_rotations,
    preset_shifts,
    totals,
)
print(shifts_matrix)
f_path_out = excel.copy_excel_file(f_path, "_solved")
excel.save_shifts(f_path_out, sheet_name, shifts_matrix, row_start, col_start)
