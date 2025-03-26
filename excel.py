"""Module to handle input and output of excel files"""

import pandas as pd

import state


def extract_residents(file_path: str, sheet_name: str) -> list[state.Resident]:
    """Extracts resident names & ranks from columns A & B.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to extract data from
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    residents = []
    lastrank = None
    for _, row in df.iterrows():
        if pd.notna(row[0]):
            lastrank = row[0]
        if pd.notna(row[1]):
            residents.append(state.Resident(row[1], lastrank))

    return residents


def extract_days(file_path: str, sheet_name: str) -> list[state.Day]:
    """Extracts day numbers and weekdays from rows 2 & 3.

    args:
        file_path: The path to the Excel file
        sheet_name: The name of the sheet to extract data from
    """

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    day_numbers = df.iloc[1, 2:].dropna().tolist()
    weekdays = df.iloc[2, 2:].dropna().tolist()

    days = [
        state.Day(number, weekday) for number, weekday in zip(day_numbers, weekdays)
    ]

    return days


if __name__ == "__main__":
    residents = extract_residents("data/Guardias enero.xlsx", "Enero 2025")
    days = extract_days("data/Guardias enero.xlsx", "Enero 2025")
    print(len(residents), residents)
    print(len(days), days)
