from datetime import date, datetime, timezone
from typing import Optional, List

import caldav
from vobject.base import Component

from managers.manager import Manager
from caldav import CalendarObjectResource

class TaskManager(Manager[CalendarObjectResource]):
    def __init__(self, url: str, username: str, password: str):
        super().__init__(url, username, password)
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
        categories: Optional[List[str]] = None,
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
        new_categories: Optional[List[str]] = None,
        new_location: Optional[str] = None,
        new_url: Optional[str] = None,
        new_completed: Optional[date | datetime | str] = None,
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
        if new_completed is not None:
            self._set_or_add(td, "completed", self._parse_dt(new_completed))

        item.save()
        return item

    def complete(
        self,
        item: caldav.CalendarObjectResource,
    ) -> caldav.CalendarObjectResource:
        """Mark a task as completed (STATUS:COMPLETED, PERCENT-COMPLETE:100)."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return self.update(
            item,
            new_status="COMPLETED",
            new_percent_complete=100,
            new_completed=now,
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

            # STATUS:COMPLETED
            if "status" in td.contents and td.contents["status"]:
                val = td.contents["status"][0].value
                if val and str(val).upper() == "COMPLETED":
                    return True

            # PERCENT-COMPLETE:100 (vobject key is usually "percent-complete")
            if "percent-complete" in td.contents and td.contents["percent-complete"]:
                val = td.contents["percent-complete"][0].value
                if val is not None and str(val) == "100":
                    return True

            # COMPLETED:<timestamp> is also a strong signal
            if "completed" in td.contents and td.contents["completed"]:
                if td.contents["completed"][0].value:
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
    def _set_or_add(component: Component, key: str, value) -> None:
        """
        Set an existing vobject property or add it if absent.
        Uses .contents so we don't rely on getattr()/normalized attribute names.
        """
        key = key.lower()
        if key in component.contents and component.contents[key]:
            component.contents[key][0].value = value
        else:
            component.add(key).value = value


    def get(self, uid: str) -> caldav.CalendarObjectResource | None:
        """
        Find a single VTODO by its iCal UID.
        Returns the first match, or None if not found.
        """
        # Some CalDAV servers support uid=... in search(); some don't.
        try:
            results = self.calendar.search(uid=uid, todo=True)
            if results:
                return results[0]
        except TypeError:
            pass

        # Fallback: scan all todos and match UID client-side
        for item in self.calendar.search(todo=True):
            v = item.vobject_instance
            if not hasattr(v, "vtodo"):
                continue
            td = v.vtodo
            if str(td.contents["uid"][0].value) == uid:
                return item

        return None

    def summary(self, *, include_completed: bool = False) -> str:
        """
        Return a string list of tasks.
        Each item displays: title, UID, status, due/start (if any).
        """
        items = self.list(include_completed=include_completed)

        def _fmt_dt(dt: object) -> str:
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d %H:%M")
            try:
                return dt.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
            except Exception:
                return str(dt)

        lines: list[str] = []
        for item in items:
            v = item.vobject_instance
            if not hasattr(v, "vtodo"):
                continue
            td = v.vtodo

            title = "(no title)"
            if "summary" in td.contents and td.contents["summary"] and td.contents["summary"][0].value:
                title = str(td.contents["summary"][0].value)

            uid = None
            if "uid" in td.contents and td.contents["uid"] and td.contents["uid"][0].value:
                uid = str(td.contents["uid"][0].value)

            status = None
            if "status" in td.contents and td.contents["status"] and td.contents["status"][0].value:
                status = str(td.contents["status"][0].value)

            due = None
            if "due" in td.contents and td.contents["due"] and td.contents["due"][0].value:
                due = td.contents["due"][0].value

            start = None
            if "dtstart" in td.contents and td.contents["dtstart"] and td.contents["dtstart"][0].value:
                start = td.contents["dtstart"][0].value

            desc = None
            if "description" in td.contents and td.contents["description"] and td.contents["description"][0].value:
                desc = td.contents["description"][0].value

            lines.append(f"- {title}")
            if uid:
                lines.append(f"  UID: {uid}")
            if desc:
                lines.append(f"  Description: {desc}")
            if status:
                lines.append(f"  Status: {status}")
            if start is not None:
                lines.append(f"  Start: {_fmt_dt(start)}")
            if due is not None:
                lines.append(f"  Due: {_fmt_dt(due)}")
            lines.append("")

        if not lines:
            return "No tasks."

        if lines[-1] == "":
            lines.pop()

        return "\n".join(lines)