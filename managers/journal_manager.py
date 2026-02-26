from datetime import datetime, time, timedelta
import caldav
from caldav import CalendarObjectResource

from managers.manager import Manager


class JournalManager(Manager[CalendarObjectResource]):
    def __init__(self, url: str, username: str, password: str):
        super().__init__(url, username, password)
        self.calendar = self.client.calendar(url=url)

    def list(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[CalendarObjectResource]:
        # Default start_date = today at 00:00 (local time)
        if start_date is None:
            today = datetime.now().date()
            start_date = datetime.combine(today, time.min)

        # Journals don’t always have natural “end”, but caldav search with a window
        # is still useful to keep results bounded and fast.
        if end_date is None:
            end_date = start_date + timedelta(days=30)

        # expand=True is not relevant for journals (no recurrences), so keep it off.
        return self.calendar.search(
            start=start_date,
            end=end_date,
            journal=True,
        )

    def add(self, title: str, desc: str = "") -> CalendarObjectResource:
        return self.calendar.save_journal(summary=title, description=desc)

    def delete(self, item: CalendarObjectResource) -> None:
        item.delete()

    def update(
        self,
        item: CalendarObjectResource,
        *,
        new_title: str | None = None,
        new_desc: str | None = None,
    ) -> CalendarObjectResource:
        v = item.vobject_instance
        if not hasattr(v, "vjournal"):
            raise ValueError("Not a VJOURNAL")

        j = v.vjournal

        if new_title is not None:
            if hasattr(j, "summary"):
                j.summary.value = new_title
            else:
                j.add("summary").value = new_title

        if new_desc is not None:
            if hasattr(j, "description"):
                j.description.value = new_desc
            else:
                j.add("description").value = new_desc

        item.save()
        return item

    def summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> str:
        """
        Render journals as:
        - YYYY-MM-DD HH:MM  Title
          Description: ...
        """
        items = self.list(start_date=start_date, end_date=end_date)
        if limit is not None:
            items = items[:limit]

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
            if not hasattr(v, "vjournal"):
                continue
            j = v.vjournal

            title = str(j.summary.value)
            uid = str(j.uid.value)
            desc = ""
            if (
                hasattr(j, "description")
                and hasattr(j.description, "value")
                and j.description.value
            ):
                desc = str(j.description.value)

            # Journals may expose a date-like field as DTSTAMP or DTSTART depending on server/client.
            # We’ll pick the best available in this order.
            dt = None
            if hasattr(j, "dtstart") and hasattr(j.dtstart, "value"):
                dt = j.dtstart.value
            elif hasattr(j, "dtstamp") and hasattr(j.dtstamp, "value"):
                dt = j.dtstamp.value
            elif hasattr(j, "created") and hasattr(j.created, "value"):
                dt = j.created.value

            when = _fmt_dt(dt) if dt is not None else "(no date)"

            lines.append(f"- {when}  {title}")
            lines.append(f"  UID: {uid}")
            if desc:
                lines.append(f"  Description: {desc}")
            lines.append("")

        if not lines:
            return "No journals."

        if lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def get(self, uid: str) -> CalendarObjectResource | None:
        """
        Find a single VJOURNAL by its iCal UID.
        Returns the first match, or None if not found.
        """
        # Some CalDAV servers support uid=... in search() for journals; try it first.
        try:
            results = self.calendar.search(uid=uid, journal=True)
            if results:
                return results[0]
        except TypeError:
            # Backend doesn't accept uid=... in search()
            pass

        # Fallback: scan a bounded window and match UID client-side.
        for item in self.list():
            v = item.vobject_instance
            if not hasattr(v, "vjournal"):
                continue
            j = v.vjournal
            if hasattr(j, "uid") and hasattr(j.uid, "value") and j.uid.value == uid:
                return item

        return None