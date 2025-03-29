"""Module to handle input and output of excel files"""

import shutil

import pandas as pd
from openpyxl import load_workbook

import state


def load_residents(file_path: str, sheet_name: str) -> list[state.Resident]:
    """loads resident names & ranks from columns A & B.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to load data from

    returns:
        A list of Resident objects
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    ROW_BOUNDS = (3, 23)

    residents = []
    for i, row in df.iterrows():
        if is_rowcol_in_bounds(i, ROW_BOUNDS):
            if pd.notna(row[0]):
                lastrank = row[0]

            residents.append(state.Resident(row[1], lastrank))

    return residents


def load_days(file_path: str, sheet_name: str) -> list[state.Day]:
    """loads day numbers and weekdays from rows 2 & 3.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to load data from

    returns:
        A list of Day objects
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    COL_BOUNDS = (2, 35)

    day_numbers = df.iloc[1, COL_BOUNDS[0] : COL_BOUNDS[1]].dropna().tolist()
    weekdays = df.iloc[2, COL_BOUNDS[0] : COL_BOUNDS[1]].dropna().tolist()

    days = [
        state.Day(number, weekday) for number, weekday in zip(day_numbers, weekdays)
    ]

    return days


def load_restrictions(
    file_path: str, sheet_name: str, type_: str
) -> list[tuple[int, int]]:
    """loads restrictions from the Excel file.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to load data from
        type_: The type of restriction

    returns:
        A list of restricted (resident_index, day_index) tuples with the restrictions
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    ROW_OFFSET = 3
    COL_OFFSET = 2

    ROW_BOUNDS = (ROW_OFFSET, 23)
    COL_BOUNDS = (COL_OFFSET, 35)

    positions = [
        (row_idx - ROW_OFFSET, col_idx - COL_OFFSET)
        for row_idx, row in df.iterrows()
        for col_idx, cell in enumerate(row)
        if is_cell_in_bounds(row_idx, col_idx, ROW_BOUNDS, COL_BOUNDS) and cell == type_
    ]

    return positions


def is_cell_in_bounds(
    row_idx: int, col_idx: int, row_bounds: tuple[int, int], col_bounds: tuple[int, int]
) -> bool:
    """Check if a cell is in the bounds of the table

    args:
        row_idx: The row index of the cell
        col_idx: The column index of the cell
        row_bounds: The bounds of the rows
        col_bounds: The bounds of the columns

    returns:
        True if the cell is in the bounds, False otherwise
    """
    return is_rowcol_in_bounds(row_idx, row_bounds) and is_rowcol_in_bounds(
        col_idx, col_bounds
    )


def is_rowcol_in_bounds(idx: int, bounds: tuple[int, int]) -> bool:
    """Check if a row or column is in the bounds of the table

    args:
        idx: The row or column index
        bounds: The bounds of the row or column

    returns:
        True if the row or column is in the bounds, False otherwise
    """
    return bounds[0] <= idx <= bounds[1]


def load_totals(file_path: str, sheet_name: str) -> list[list[int]]:
    """loads totals from the Excel file.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to load data from

    returns:
        A matrix of total shifts of each type for each resident, rows are residents, columns are shift types
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    ROW_BOUNDS = (2, 22)
    COL_BOUNDS = (1, 4)

    totals = []
    for row_idx, row in df.iterrows():
        if is_rowcol_in_bounds(row_idx, ROW_BOUNDS):
            shifts = []
            for col_idx, cell in enumerate(row):
                if is_rowcol_in_bounds(col_idx, COL_BOUNDS):
                    shifts.append(cell)

            totals.append(shifts)

    return totals


import os
import shutil


def copy_excel_file(original_path: str, fname_extension: str):
    """Copies an Excel file and saves it with a new filename in the same directory.

    args:
        original_path: The path to the original Excel file
        fname_extension: A string to add to the original filename

    returns:
        The path of the copied file
    """
    # Define the new file path
    new_path = original_path[:-5] + fname_extension + ".xlsx"

    # Copy the file
    shutil.copy2(original_path, new_path)

    return new_path  # Return the path of the copied file


def save_shifts(file_path: str, sheet_name: str, shift_matrix: list[list[str]]):
    """Introduces the shifts into a given Excel file

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to save data to
        shift_matrix: The matrix of shifts to save
    """

    # Load the existing workbook
    wb = load_workbook(file_path)

    # Select the sheet
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in the workbook.")

    sheet = wb[sheet_name]

    ROW_OFFSET = 3
    COL_OFFSET = 2

    for i, row in enumerate(shift_matrix):
        for j, shift in enumerate(row):
            if shift:
                sheet.cell(
                    row=i + ROW_OFFSET + 1, column=j + COL_OFFSET + 1, value=shift
                )

        wb.save(file_path)


# TODO: Add function to load totals of Sabados and Viernes-Domingos
# TODO: Add function to save updated totals


if __name__ == "__main__":
    residents = load_residents("data/Guardias enero.xlsx", "Enero 2025")
    days = load_days("data/Guardias enero.xlsx", "Enero 2025")
    v_positions = load_restrictions("data/Guardias enero.xlsx", "Enero 2025", "V")
    u_positions = load_restrictions("data/Guardias enero.xlsx", "Enero 2025", "U")
    ut_positions = load_restrictions("data/Guardias enero.xlsx", "Enero 2025", "UT")
    totals = load_totals("data/Guardias enero.xlsx", "Global")
    print(len(residents), residents)
    print(len(days), days)
    print(v_positions)
    print(u_positions)
    print(ut_positions)
    print(totals)
