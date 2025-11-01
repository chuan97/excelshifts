"""Module with dataclasses to hold the state for the main entities of the program"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

__all__ = ["Day", "Resident", "ShiftType", "Instance", "Rank", "WEEKDAYS"]

WEEKDAYS = ("L", "M", "X", "J", "V", "S", "D")

Rank = Literal["R1", "R2", "R3", "R4"]


@dataclass(frozen=True, slots=True)
class Day:
    """Class to represent a given day of the month

    Attributes:
        number: The day of the month
        day_of_week: The day of the week
    """

    number: int
    day_of_week: str

    def __post_init__(self):
        if self.number < 1 or self.number > 31:
            raise ValueError("Day number must be between 1 and 31")
        if self.day_of_week not in WEEKDAYS:
            raise ValueError(
                "Day of the week must be one of 'L', 'M', 'X', 'J', 'V', 'S', 'D'"
            )


@dataclass(frozen=True, slots=True)
class Resident:
    """Class to represent a resident

    Attributes:
        name: The name of the resident
        rank: The rank of the resident
    """

    name: str
    rank: Rank

    def __post_init__(self):
        if self.rank not in ("R1", "R2", "R3", "R4", "RE"):
            raise ValueError("Rank must be one of 'R1', 'R2', 'R3', 'R4', 'RE'")


class ShiftType(Enum):
    """Enum to represent the type of a shift"""

    R = 0
    G = 1
    T = 2
    M = 3


@dataclass(frozen=True, slots=True)
class Instance:
    """Canonical in-memory representation of a scheduling month.

    Attributes:
        residents: Tuple of residents
        days: Tuple of days
        v_positions: Tuple of (resident_idx, day_idx) tuples for V positions
        u_positions: Tuple of (resident_idx, day_idx) tuples for U positions
        ut_positions: Tuple of (resident_idx, day_idx) tuples for UT positions
        p_positions: Tuple of (resident_idx, day_idx) tuples for P positions
        external_rotations: Frozenset of resident_idx who are on external rotation
        presets: Tuple of preset assignments as (resident_idx, day_idx, shift_type)
        end_of_month: Index of the first day of the next month in days list (derived)
        p_days: Frozenset of day indices that are holidays (derived)
    """

    residents: tuple[Resident, ...]
    days: tuple[Day, ...]
    v_positions: tuple[tuple[int, int], ...]
    u_positions: tuple[tuple[int, int], ...]
    ut_positions: tuple[tuple[int, int], ...]
    p_positions: tuple[tuple[int, int], ...]
    extra_p_days: tuple[int, ...]
    external_rotations: frozenset[int]
    presets: tuple[tuple[int, int, int], ...]

    end_of_month: int = field(init=False)
    p_days: frozenset[int] = field(init=False)

    def __post_init__(self):
        # Detect end of month: first index where day number decreases; else len(days)
        eom = len(self.days)
        for idx in range(1, len(self.days)):
            if self.days[idx].number < self.days[idx - 1].number:
                eom = idx
                break
        object.__setattr__(self, "end_of_month", eom)

        # Compute holiday indices from p_positions and extra_p_days
        pset = set(day_idx for (_, day_idx) in self.p_positions)
        for day_idx, day in enumerate(self.days):
            if day.number in self.extra_p_days:
                pset.add(day_idx)
        object.__setattr__(self, "p_days", frozenset(pset))
