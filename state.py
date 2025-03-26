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


class ResidentRank(Enum):
    """Enum to represent the rank of a resident"""

    r1 = 1
    r2 = 2
    r3 = 3
    r4 = 4
    ext = 5


@dataclass(frozen=True)
class Resident:
    """Class to represent a resident

    args:
        name: The name of the resident
        rank: The rank of the resident
    """

    name: str
    rank: ResidentRank


class ShiftType(Enum):
    """Enum to represent the type of a shift"""

    R = 1
    G = 2
    T = 3
    M = 4
