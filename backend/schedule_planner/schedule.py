"""Lays out one week of study at a time, then the next, across an exam session.

The shape of a week: available time is split into blocks of `study_block_size` minutes
around fixed meal breaks. Each day picks a few subjects whose exam has not passed,
groups their learning blocks together, and ends with exactly one short recall block per
subject studied that day. How much each subject gets is a weight over remaining workload,
difficulty against priority, and how close its exam is.

Weekly targets are approximate: block boundaries and exam dates constrain them. A subject's
`max_study_hours` caps its cumulative *active learning*; recall is exempt, which is why
total hours can exceed the cap. Regenerating the current week replaces its plan without
counting it twice, and weeks already left behind are history the next week builds on.
"""
import datetime as dt

from .dayrange import DayRange

# Subjects per day are capped at a third of the day's blocks, so learning stays grouped.
BLOCKS_PER_SUBJECT = 3
# The workload estimate: ECTS times this, minus the lectures already attended.
HOURS_PER_ECTS = 30
WEEKS_IN_SEMESTER = 13


class Schedule:
    def __init__(self, user_input: dict, start_time: str, end_time: str,
                 lunch_time: tuple[str, str], dinner_time: tuple[str, str],
                 alpha: float = .3, beta: float = 5,
                 weeks_in_semester: int = WEEKS_IN_SEMESTER,
                 hours_per_week_budget: float | None = None):
        # ---------- Inputs ----------
        self.user_input = user_input
        self.subjects = user_input["subjects"]
        self.days_off = user_input["days_off"]
        self.exam_session = user_input["exam_session"]

        self.start_time = start_time
        self.end_time = end_time
        self.lunch_time = lunch_time
        self.dinner_time = dinner_time

        # ---------- Parameters ----------
        self.alpha = alpha
        self.beta = beta
        self.weeks_in_semester = weeks_in_semester
        # A week's study budget. None fills every free slot, which is the notebook's behaviour.
        self.hours_per_week_budget = hours_per_week_budget
        if (hours_per_week_budget is not None
                and (not isinstance(hours_per_week_budget, (int, float)) or hours_per_week_budget < 0)):
            raise ValueError("The weekly study budget must be a non-negative number of hours.")
        self.study_block_size = user_input.get("study_block_size", 90)
        if type(self.study_block_size) is not int or self.study_block_size <= 0:
            raise ValueError("study_block_size must be a positive integer.")
        for subject in self.subjects.values():
            limit = subject.get("max_study_hours")
            if limit is not None and (not isinstance(limit, (int, float))
                                      or not 0 <= limit < float("inf")):
                raise ValueError("max_study_hours must be finite and non-negative.")

        # ---------- State ----------
        self.hours_per_week = 0.0
        # Scheduled history, keyed by date so a regenerated week is not counted twice.
        # Seeded from `history` so a run that starts mid-session knows what came before.
        self.study_history: dict[dt.date, list[tuple[str, str, float]]] = {}
        for entry in user_input.get("history", []):
            self.study_history.setdefault(entry["date"], []).append(
                (entry["subject"], entry["type"], entry["hours"]))
        self.block_types: dict[dt.date, dict[tuple[str, str], str]] = {}
        self.schedule: dict[dt.date, dict[tuple[str, str], str]] = {}
        self.current_week: DayRange | None = None
        self.days_off_this_week: list[DayRange] = []
        self.hours_per_subject_this_week = {name: None for name in self.subjects}
        # One entry per week planned so far, by its position in the exam session.
        self.weeks: dict[int, dict] = {}

        start = self.exam_session.start_date
        self.set_week(DayRange.from_date(start, min(7, len(self.exam_session))))

    # ---------- Week management ----------

    def set_week(self, week: DayRange) -> None:
        """Make `week` the current one, moving any planned week into history."""
        if not isinstance(week, DayRange):
            raise TypeError("week must be a DayRange.")
        if (week.start_date < self.exam_session.start_date
                or week.end_date > self.exam_session.end_date):
            raise ValueError("Week must be inside the exam session.")

        if self.current_week is not None:
            for day, blocks in self.schedule.items():
                self.study_history[day] = [
                    (subject, self.block_types.get(day, {}).get(slot, "active_learning"),
                     (self._to_minutes(slot[1]) - self._to_minutes(slot[0])) / 60)
                    for slot, subject in blocks.items()
                ]

        self.current_week = week
        self.days_off_this_week = [
            overlap for day_range in self.days_off
            if (overlap := week.intersection(day_range)) is not None
        ]
        self.hours_per_subject_this_week = {name: None for name in self.subjects}
        self.schedule = {day: {} for day in week}
        self.block_types = {day: {} for day in week}
        self.hours_per_week = self._budget_hours()

    def next_week(self) -> None:
        """Advance to the next week of the exam session, if one remains."""
        if self.current_week.end_date >= self.exam_session.end_date:
            raise ValueError("Already at the end of the exam session.")
        start = self.current_week.end_date + dt.timedelta(days=1)
        remaining = (self.exam_session.end_date - start).days + 1
        self.set_week(DayRange.from_date(start, min(7, remaining)))

    @property
    def week_index(self) -> int:
        """Which week of the exam session is current, counting from zero."""
        return (self.current_week.start_date - self.exam_session.start_date).days // 7

    # ---------- Time utilities ----------

    @staticmethod
    def _to_minutes(time_str: str) -> int:
        return 60 * int(time_str[:2]) + int(time_str[3:])

    @staticmethod
    def _to_time(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _time_slots(self) -> list[tuple[int, int, str | None]]:
        """The day as (start, end, meal) triples: study blocks have meal None."""
        start = self._to_minutes(self.start_time)
        end = self._to_minutes(self.end_time)
        if start >= end:
            raise ValueError("start_time must precede end_time.")

        meals = [("Lunch", *map(self._to_minutes, self.lunch_time)),
                 ("Dinner", *map(self._to_minutes, self.dinner_time))]
        boundaries = {start, end}
        for name, a, b in meals:
            if a >= b:
                raise ValueError(f"Invalid {name.lower()} interval.")
            if start < a < end:
                boundaries.add(a)
            if start < b < end:
                boundaries.add(b)

        slots = []
        for a, b in zip(sorted(boundaries), sorted(boundaries)[1:]):
            meal = next((name for name, x, y in meals if x <= a and b <= y), None)
            if meal is not None:
                slots.append((a, b, meal))
                continue
            while a < b:
                cut = min(a + self.study_block_size, b)
                slots.append((a, cut, None))
                a = cut
        return slots

    def _is_day_off(self, day: dt.date) -> bool:
        return any(day in day_range for day_range in self.days_off_this_week)

    def _study_days(self) -> int:
        return sum(1 for day in self.current_week if not self._is_day_off(day))

    def _available_hours(self) -> float:
        """Hours of free slots this week, days off excluded. What the week physically offers."""
        minutes = sum(b - a for a, b, meal in self._time_slots() if meal is None)
        return minutes / 60 * self._study_days()

    def _budget_hours(self) -> float:
        """Hours the week may plan: the free slots, or the user's budget if that is lower.

        A budget is pro-rated over the days of a part week, so a two-day week gets two
        sevenths of it. Recall blocks are placed regardless, as they are for max_study_hours,
        so a week with a tight budget can end slightly above it.
        """
        free = self._available_hours()
        if self.hours_per_week_budget is None:
            return free
        return min(free, self.hours_per_week_budget * len(self.current_week) / 7)

    # ---------- Allocation ----------

    def get_days_until_exam(self, subject: str) -> int:
        """Days from the start of the current week to the subject's exam."""
        return (self.subjects[subject]["examdate"].start_date - self.current_week.start_date).days

    def get_hours_studied_per_week(self, subject: str) -> float:
        """Hours scheduled for a subject in the current week, recall included."""
        return sum((self._to_minutes(end) - self._to_minutes(start)) / 60
                   for blocks in self.schedule.values()
                   for (start, end), name in blocks.items() if name == subject)

    def _previous_hours(self, subject: str, active_only: bool = False) -> float:
        return sum(hours for day, blocks in self.study_history.items()
                   if day < self.current_week.start_date
                   for name, kind, hours in blocks
                   if name == subject and (not active_only or kind == "active_learning"))

    @property
    def hours_studied_per_subject(self) -> dict[str, float]:
        """Scheduled totals before and during the current week."""
        return {name: self._previous_hours(name) + self.get_hours_studied_per_week(name)
                for name in self.subjects}

    def generate_hours_per_subject_per_week(self) -> dict[str, float]:
        """Split the week's plannable hours over the subjects by weight."""
        self.hours_per_week = self._budget_hours()
        weights = {}
        for name, subject in self.subjects.items():
            days = self.get_days_until_exam(name)
            if days <= 0:
                weights[name] = 0.0
                continue
            studied = self._previous_hours(name)
            workload = max(0, HOURS_PER_ECTS * subject["ects"]
                           - self.weeks_in_semester * subject["lecture_per_week"] - studied)
            # Keep a recall allocation once the learning workload is exhausted.
            weights[name] = max(self.study_block_size / 60, workload)
            weights[name] *= (subject["difficulty"] / subject["priority"]) ** self.alpha
            weights[name] *= self.beta ** (-1 / (days + studied))
        total = sum(weights.values())
        return {name: weight / total * self.hours_per_week if total else 0.0
                for name, weight in weights.items()}

    # ---------- Generation ----------

    def generate_schedule(self) -> dict:
        """Plan the current week: grouped learning, then one recall block per subject studied.

        Replaces whatever was planned for this week before, so calling it twice is a no-op.
        """
        self.schedule = {day: {} for day in self.current_week}
        self.block_types = {day: {} for day in self.current_week}
        self.hours_per_subject_this_week = self.generate_hours_per_subject_per_week()
        assigned = {name: 0.0 for name in self.subjects}
        active = {name: self._previous_hours(name, active_only=True) for name in self.subjects}
        slots = [(a, b) for a, b, meal in self._time_slots() if meal is None]
        block_hours = self.study_block_size / 60

        def remaining(name):
            limit = self.subjects[name].get("max_study_hours")
            return max(0.0, limit - active[name]) if limit is not None else float("inf")

        def deficit(name, extra=0.0):
            return self.hours_per_subject_this_week[name] - assigned[name] - extra

        def days_left(from_day):
            return sum(1 for day in self.current_week
                       if day >= from_day and not self._is_day_off(day))

        def put(day, a, b, name, kind):
            slot = (self._to_time(a), self._to_time(b))
            self.schedule[day][slot] = name
            self.block_types[day][slot] = kind
            hours = (b - a) / 60
            assigned[name] += hours
            if kind == "active_learning":
                active[name] += hours

        for day in self.current_week:
            if self._is_day_off(day) or not slots:
                continue
            eligible = [name for name, subject in self.subjects.items()
                        if day < subject["examdate"].start_date]
            if not eligible:
                continue
            eligible.sort(key=deficit, reverse=True)

            # Reserve an evening recall for every subject taken on, and normally keep at
            # least BLOCKS_PER_SUBJECT learning blocks together before switching subject.
            count = min(len(eligible), max(1, len(slots) // BLOCKS_PER_SUBJECT))
            selected = eligible[:count]
            if all(remaining(name) * 60 < 1 for name in eligible):
                # Nothing left to learn: recall as many subjects as the day holds.
                selected = eligible[:len(slots)]
            recall_slots = slots[-len(selected):]
            learning_slots = slots[:-len(selected)]
            allocations = {name: 0 for name in selected}
            reserved = {name: (b - a) / 60 for name, (a, b) in zip(selected, recall_slots)}

            # Hand out block counts by deficit, then lay them out subject by subject.
            # With a budget, the day stops early rather than filling every free slot; the
            # recall blocks are reserved already and are always placed.
            day_budget = None if self.hours_per_week_budget is None else max(
                0.0, self._budget_hours() - sum(assigned.values())
                - sum(reserved.values())) / max(1, days_left(day))
            for _ in learning_slots:
                if day_budget is not None and sum(allocations.values()) * block_hours >= day_budget:
                    break
                candidates = [name for name in selected
                              if (remaining(name) - allocations[name] * block_hours) * 60 >= 1]
                if not candidates:
                    break
                allocations[max(candidates, key=lambda name: deficit(
                    name, reserved[name] + allocations[name] * block_hours))] += 1

            index = 0
            for name in selected:
                for _ in range(allocations[name]):
                    a, b = learning_slots[index]
                    index += 1
                    # A partial block enforces the cap to the minute.
                    minutes = remaining(name) * 60
                    if minutes < b - a:
                        b = a + int(minutes + 1e-9)
                    if b > a:
                        put(day, a, b, name, "active_learning")
            for name, (a, b) in zip(selected, recall_slots):
                put(day, a, b, name, "recall")

        self.weeks[self.week_index] = self._week_record()
        return self.schedule

    # ---------- Output ----------

    def _week_record(self) -> dict:
        """The current week as plain JSON values."""
        meals = [(a, b, name) for a, b, name in self._time_slots() if name is not None]
        scheduled = {name: 0.0 for name in self.subjects}
        active = {name: 0.0 for name in self.subjects}
        days = []
        for day in self.current_week:
            off = self._is_day_off(day)
            blocks = []
            if not off:
                for (start, end), name in self.schedule[day].items():
                    kind = self.block_types[day][(start, end)]
                    minutes = self._to_minutes(end) - self._to_minutes(start)
                    blocks.append({"start_time": start, "end_time": end,
                                   "duration_minutes": minutes, "type": kind,
                                   "subject": name, "label": None})
                    scheduled[name] += minutes / 60
                    if kind == "active_learning":
                        active[name] += minutes / 60
                blocks += [{"start_time": self._to_time(a), "end_time": self._to_time(b),
                            "duration_minutes": b - a, "type": "meal",
                            "subject": None, "label": meal} for a, b, meal in meals]
                blocks.sort(key=lambda block: (block["start_time"], block["end_time"]))
            days.append({"date": day.isoformat(), "is_day_off": off, "blocks": blocks})
        return {"start_date": self.current_week.start_date.isoformat(),
                "end_date": self.current_week.end_date.isoformat(),
                "range_length": len(self.current_week),
                "available_hours": self._available_hours(),
                "budget_hours": self._budget_hours(),
                "target_hours_per_subject": dict(self.hours_per_subject_this_week),
                "scheduled_hours_per_subject": scheduled,
                "active_learning_hours_per_subject": active,
                "days": days}

    def to_dict(self) -> dict:
        """Every week planned so far, with running and final totals."""
        total = {name: 0.0 for name in self.subjects}
        total_active = {name: 0.0 for name in self.subjects}
        weeks = []
        for index in sorted(self.weeks):
            week = dict(self.weeks[index])
            for name, hours in week["scheduled_hours_per_subject"].items():
                total[name] += hours
            for name, hours in week["active_learning_hours_per_subject"].items():
                total_active[name] += hours
            week["cumulative_hours_per_subject"] = dict(total)
            weeks.append(week)
        return {"exam_session": {"start_date": self.exam_session.start_date.isoformat(),
                                "range_length": len(self.exam_session)},
                "study_block_size": self.study_block_size,
                "weeks": weeks,
                "summary": {"scheduled_hours_per_subject": total,
                            "active_learning_hours_per_subject": total_active}}
