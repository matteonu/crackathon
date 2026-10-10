"""A run of consecutive days, the unit the scheduler works in.

An exam session, a holiday and an exam date are all DayRanges; only their length differs.
`from_value` accepts the three shapes the JSON input uses, so the HTTP layer never builds
dates by hand.
"""
import datetime as dt
from dataclasses import dataclass
from typing import Iterator


def iso_date(value) -> dt.date:
    """Parse 'YYYY-MM-DD'. Anything else is a ValueError, including other ISO spellings."""
    if not isinstance(value, str):
        raise ValueError("A date must be a string like '2026-11-20'.")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{value!r} is not a date like '2026-11-20'.") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{value!r} is not a date like '2026-11-20'.")
    return parsed


@dataclass(frozen=True)
class DayRange:
    start_day: int
    start_month: int
    start_year: int
    range_length: int

    def __post_init__(self):
        if type(self.range_length) is not int or self.range_length < 1:
            raise ValueError("range_length must be a positive integer.")
        # Validate the starting date and the range bounds.
        _ = self.end_date

    # ---------- Construction ----------

    @classmethod
    def from_date(cls, day: dt.date, range_length: int = 1) -> "DayRange":
        return cls(day.day, day.month, day.year, range_length)

    @classmethod
    def from_value(cls, value) -> "DayRange":
        """A DayRange, an ISO date string (one day), or {'start_date', 'range_length'}."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls.from_date(iso_date(value))
        if isinstance(value, dict):
            if "start_date" not in value:
                raise ValueError("A date range needs a start_date.")
            return cls.from_date(iso_date(value["start_date"]), value.get("range_length", 1))
        raise ValueError("A date range must be an ISO date or {start_date, range_length}.")

    # ---------- Dates ----------

    @property
    def start_date(self) -> dt.date:
        try:
            return dt.date(self.start_year, self.start_month, self.start_day)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Not a valid date: {exc}") from None

    @property
    def end_date(self) -> dt.date:
        """Last day of the range (inclusive)."""
        return self.start_date + dt.timedelta(days=self.range_length - 1)

    def __len__(self) -> int:
        return self.range_length

    def __iter__(self) -> Iterator[dt.date]:
        for offset in range(len(self)):
            yield self.start_date + dt.timedelta(days=offset)

    def __getitem__(self, index):
        """Supports indexing and slicing."""
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if not isinstance(index, int):
            raise TypeError("Index must be an integer or slice.")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("Day index out of range.")
        return self.start_date + dt.timedelta(days=index)

    def __contains__(self, day) -> bool:
        return isinstance(day, dt.date) and self.start_date <= day <= self.end_date

    def __add__(self, days: int) -> "DayRange":
        """Shift the entire range forward by a number of days."""
        if not isinstance(days, int):
            return NotImplemented
        return DayRange.from_date(self.start_date + dt.timedelta(days=days), len(self))

    __radd__ = __add__

    def __sub__(self, days: int) -> "DayRange":
        """Shift the entire range backward by a number of days."""
        if not isinstance(days, int):
            return NotImplemented
        return self + (-days)

    # ---------- Queries ----------

    def index(self, day: dt.date) -> int:
        """The zero-based position of a date in the range."""
        if day not in self:
            raise ValueError(f"{day} is not in the range.")
        return (day - self.start_date).days

    def add_days(self, day: dt.date, days: int) -> dt.date:
        """Add days to a date without leaving the range."""
        if day not in self:
            raise ValueError("Starting date is outside the range.")
        result = day + dt.timedelta(days=days)
        if result not in self:
            raise ValueError("Resulting date is outside the range.")
        return result

    def overlaps(self, other: "DayRange") -> bool:
        return self.start_date <= other.end_date and other.start_date <= self.end_date

    def intersection(self, other: "DayRange") -> "DayRange | None":
        """The common date range, if any."""
        start = max(self.start_date, other.start_date)
        end = min(self.end_date, other.end_date)
        if start > end:
            return None
        return DayRange.from_date(start, (end - start).days + 1)
