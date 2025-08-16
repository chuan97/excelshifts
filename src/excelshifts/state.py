"""Module with dataclasses to hold the state for the main entities of the program"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Day:
    """Class to represent a given day of the month

    args:
        number: The day of the month
        day_of_week: The day of the week
    """

    number: int
    day_of_week: str

    def __post_init__(self):
        if self.number < 1 or self.number > 31:
            raise ValueError("Day number must be between 1 and 31")
        if self.day_of_week not in ["L", "M", "X", "J", "V", "S", "D"]:
            raise ValueError(
                "Day of the week must be one of 'L', 'M', 'X', 'J', 'V', 'S', 'D'"
            )


@dataclass(frozen=True)
class Resident:
    """Class to represent a resident

    args:
        name: The name of the resident
        rank: The rank of the resident
    """

    name: str
    rank: str

    def __post_init__(self):
        if self.rank not in ["R1", "R2", "R3", "R4"]:
            raise ValueError("Rank must be one of 'R1', 'R2', 'R3', 'R4'")


class ShiftType(Enum):
    """Enum to represent the type of a shift"""

    R = 1
    G = 2
    T = 3
    M = 4
