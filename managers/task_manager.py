from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import caldav
import vobject


class TaskManager:
    def __init__(self, url: str, username: str, password: str):
        self.url = url
        self.client = caldav.DAVClient(url, username=username, password=password)
        self.calendar = self.client.calendar(url=url)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        include_completed: bool = False,
    ) -> list[caldav.CalendarObjectResource]:
        """Return all VTODO items in the calendar.

        By default completed tasks (STATUS:COMPLETED / PERCENT-COMPLETE:100)
        are excluded, mirroring the typical UI behaviour.
        """
        todos = self.calendar.search(todo=True)
        if include_completed:
            return todos
        return [t for t in todos if not self._is_completed(t)]

    def get(self, url: str) -> caldav.CalendarObjectResource:
        """Fetch a single task by its URL."""
        return self.calendar.object_by_url(url)

    def add(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        priority: int = 5,
        due: Optional[date | datetime | str] = None,
        start: Optional[date | datetime | str] = None,
        status: Optional[str] = None,
        percent_complete: Optional[int] = None,
        categories: Optional[list[str]] = None,
        location: Optional[str] = None,
        url: Optional[str] = None,
    ) -> caldav.CalendarObjectResource:
        """Create a new task and return the saved object.

        Parameters
        ----------
        title:            Summary / title of the task.
        description:      Free-text description.
        priority:         1 (highest) … 9 (lowest), 0 = undefined.  Default 5.
        due:              Due date/datetime.  Accepts a ``date``, ``datetime``
                          or an ISO-8601 string (``YYYY-MM-DD`` or full ISO).
        start:            Start date (DTSTART).
        status:           ``NEEDS-ACTION`` | ``IN-PROCESS`` | ``COMPLETED`` |
                          ``CANCELLED``.
        percent_complete: 0–100.
        categories:       List of category strings.
        location:         Location string.
        url:              Related URL.
        """
        kwargs: dict = {
            "summary": title,
            "priority": priority,
        }
        if description is not None:
            kwargs["description"] = description
        if due is not None:
            kwargs["due"] = self._parse_dt(due)
        if start is not None:
            kwargs["dtstart"] = self._parse_dt(start)
        if status is not None:
            kwargs["status"] = status.upper()
        if percent_complete is not None:
            kwargs["percent_complete"] = percent_complete
        if categories is not None:
            kwargs["categories"] = categories
        if location is not None:
            kwargs["location"] = location
        if url is not None:
            kwargs["url"] = url

        return self.calendar.save_todo(**kwargs)

    def delete(self, item: caldav.CalendarObjectResource) -> None:
        """Delete a task."""
        item.delete()

    def update(
        self,
        item: caldav.CalendarObjectResource,
        *,
        new_title: Optional[str] = None,
        new_description: Optional[str] = None,
        new_priority: Optional[int] = None,
        new_due: Optional[date | datetime | str] = None,
        new_start: Optional[date | datetime | str] = None,
        new_status: Optional[str] = None,
        new_percent_complete: Optional[int] = None,
        new_categories: Optional[list[str]] = None,
        new_location: Optional[str] = None,
        new_url: Optional[str] = None,
    ) -> caldav.CalendarObjectResource:
        """Update one or more fields of an existing task and save it.

        Only the keyword arguments that are explicitly passed (i.e. not
        ``None``) are modified; everything else is left untouched.
        """
        v = item.vobject_instance
        if not hasattr(v, "vtodo"):
            raise ValueError("The given object is not a VTODO component.")
        td = v.vtodo

        if new_title is not None:
            self._set_or_add(td, "summary", new_title)
        if new_description is not None:
            self._set_or_add(td, "description", new_description)
        if new_priority is not None:
            self._set_or_add(td, "priority", str(new_priority))
        if new_due is not None:
            self._set_or_add(td, "due", self._parse_dt(new_due))
        if new_start is not None:
            self._set_or_add(td, "dtstart", self._parse_dt(new_start))
        if new_status is not None:
            self._set_or_add(td, "status", new_status.upper())
        if new_percent_complete is not None:
            self._set_or_add(td, "percent-complete", str(new_percent_complete))
        if new_categories is not None:
            self._set_or_add(td, "categories", new_categories)
        if new_location is not None:
            self._set_or_add(td, "location", new_location)
        if new_url is not None:
            self._set_or_add(td, "url", new_url)

        item.save()
        return item

    def complete(
        self,
        item: caldav.CalendarObjectResource,
    ) -> caldav.CalendarObjectResource:
        """Mark a task as completed (STATUS:COMPLETED, PERCENT-COMPLETE:100)."""
        return self.update(
            item,
            new_status="COMPLETED",
            new_percent_complete=100,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_completed(self, item: caldav.CalendarObjectResource) -> bool:
        try:
            v = item.vobject_instance
            if not hasattr(v, "vtodo"):
                return False
            td = v.vtodo
            if hasattr(td, "status") and td.status.value.upper() == "COMPLETED":
                return True
            if (
                hasattr(td, "percent_complete")
                and str(td.percent_complete.value) == "100"
            ):
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _parse_dt(value: date | datetime | str) -> date | datetime:
        """Normalise a user-supplied date value.

        Accepts a ``date``, ``datetime``, or an ISO-8601 string and returns
        the appropriate Python object so caldav can serialise it correctly.
        """
        if isinstance(value, (date, datetime)):
            return value
        value = value.strip()
        try:
            # Full datetime (e.g. "2025-06-15T09:00:00")
            return datetime.fromisoformat(value)
        except ValueError:
            pass
        # Date only (e.g. "2025-06-15")
        return date.fromisoformat(value)

    @staticmethod
    def _set_or_add(component: vobject.Component, key: str, value) -> None:
        """Set an existing vobject property or add it if absent.

        ``key`` should be the lowercase property name (e.g. ``"summary"``).
        The normalised attribute name used by vobject replaces ``-`` with
        ``_`` (e.g. ``percent-complete`` → ``percent_complete``).
        """
        attr = key.replace("-", "_")
        if hasattr(component, attr):
            getattr(component, attr).value = value
        else:
            component.add(key).value = value

