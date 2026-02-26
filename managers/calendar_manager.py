import os
from datetime import datetime, time, timedelta
from typing import Sequence, Union

import caldav
from caldav import CalendarObjectResource

from managers.manager import Manager
from managers.utils import invite_attendees_by_icaluid, sync_caldav_google


class CalendarManager(Manager[CalendarObjectResource]):
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        *,
        google_service,
        google_calendar_id_env: str = "GOOGLE_CALENDAR_ID",
    ):
        super().__init__(url, username, password)
        self.calendar = self.client.calendar(url=url)

        self.google_service = google_service
        self.google_calendar_id = os.environ[google_calendar_id_env]

    def list(
            self,
            start_date: datetime | None = None,
            end_date: datetime | None = None,
    ) -> list[CalendarObjectResource]:

        # Default start_date = today at 00:00 (local time)
        if start_date is None:
            today = datetime.now().date()
            start_date = datetime.combine(today, time.min)

        if end_date is None:
            end_date = start_date + timedelta(days=30)

        return self.calendar.search(
            start=start_date,
            end=end_date,
            event=True,
            expand=True,
        )

    def add(self, title: str, start: datetime, end: datetime):
        return self.calendar.save_event(dtstart=start, dtend=end, summary=title)

    def delete(self, item: CalendarObjectResource):
        item.delete()

    def update(self, item: CalendarObjectResource, *, new_title=None, new_desc=None):
        v = item.vobject_instance
        if not hasattr(v, "vevent"):
            raise ValueError("Not a VEVENT")
        ev = v.vevent
        if new_title is not None:
            if hasattr(ev, "summary"):
                ev.summary.value = new_title
            else:
                ev.add("summary").value = new_title
        if new_desc is not None:
            if hasattr(ev, "description"):
                ev.description.value = new_desc
            else:
                ev.add("description").value = new_desc
        item.save()
        return item

    def invite(
        self,
        item,
        emails: Union[str, Sequence[str]],
        *,
        send_updates: str = "all",
        keep_existing: bool = True,
    ) -> dict:
        """
            Invite attendees by using Google Calendar as the scheduling/invite engine,
        AND persist the same attendees into the CalDAV VEVENT so the next vdirsyncer
        run doesn't remove them (which would trigger "canceled" emails).

        Note: the item must have already been synced to Google for this to work.
        """
        # Best-effort: ensure the event exists in Google before we patch it.
        try:
            sync_caldav_google()
        except Exception:
            print("Sync between CalDAV and Google Calendar failed, ignoring")

        v = item.vobject_instance
        if not hasattr(v, "vevent"):
            raise ValueError("Not a VEVENT")

        ev = v.vevent
        if not hasattr(ev, "uid") or not ev.uid.value:
            raise ValueError("VEVENT has no UID; cannot invite by iCalUID.")

        # Normalize emails to a de-duped list (case-insensitive), preserving order.
        if isinstance(emails, str):
            raw_emails = [emails]
        else:
            raw_emails = list(emails)

        norm_emails = []
        seen = set()
        for e in raw_emails:
            e2 = e.strip()
            if not e2:
                continue
            key = e2.lower()
            if key in seen:
                continue
            seen.add(key)
            norm_emails.append(e2)

        if not norm_emails:
            raise ValueError("No attendee emails provided.")

        ical_uid = ev.uid.value

        # 1) Invite via Google (sends emails)
        updated = invite_attendees_by_icaluid(
            self.google_service,
            ical_uid,
            norm_emails,
            send_updates=send_updates,
            keep_existing=keep_existing,
        )

        # 2) Persist attendees into the CalDAV event too, so sync won't "remove" them.
        existing_attendees = set()
        if hasattr(ev, "attendee"):
            att = ev.attendee
            # vobject: can be a list if multiple ATTENDEE properties exist
            if isinstance(att, list):
                for a in att:
                    if hasattr(a, "value") and a.value:
                        existing_attendees.add(a.value.strip().lower())
            else:
                if hasattr(att, "value") and att.value:
                    existing_attendees.add(att.value.strip().lower())

        # Add missing ATTENDEE lines
        changed = False
        for email in norm_emails:
            mailto = f"mailto:{email}"
            if mailto.lower() in existing_attendees:
                continue

            a = ev.add("attendee")
            a.value = mailto
            # Minimal params to make it sane for most clients
            a.params["CUTYPE"] = ["INDIVIDUAL"]
            a.params["ROLE"] = ["REQ-PARTICIPANT"]
            a.params["PARTSTAT"] = ["NEEDS-ACTION"]
            a.params["RSVP"] = ["TRUE"]
            changed = True

        # Ensure ORGANIZER exists (helps some clients; also reduces weirdness)
        # If you don't want this, you can remove this block.
        if not hasattr(ev, "organizer"):
            try:
                a = (
                    self.google_service.calendarList()
                    .get(calendarId="primary")
                    .execute()
                )
                primary_email = a.get("id")
                if primary_email:
                    org = ev.add("organizer")
                    org.value = f"mailto:{primary_email}"
            except Exception:
                # If we can't resolve it, don't block invites.
                pass

        if changed:
            item.save()

        return updated

    def summary(self, start_date: datetime | None = None, end_date: datetime | None = None) -> str:
        """
        Return the string to display the list of events in the calendar between the two dates.
        Each item displays: title, description, date/time, attendees (if any).
        """
        items = self.list(start_date=start_date, end_date=end_date)

        def _fmt_dt(dt: object) -> str:
            # vobject can give datetime/date-like objects; try common representations
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d %H:%M")
            # date (no time)
            try:
                return dt.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
            except Exception:
                return str(dt)

        lines: list[str] = []
        for item in items:
            v = item.vobject_instance
            if not hasattr(v, "vevent"):
                # Skip non-VEVENT components
                continue
            ev = v.vevent

            uid = ev.uid.value
            title = ev.summary.value
            desc = ev.description.value


            start = None
            end = None
            if hasattr(ev, "dtstart") and hasattr(ev.dtstart, "value"):
                start = ev.dtstart.value
            if hasattr(ev, "dtend") and hasattr(ev.dtend, "value"):
                end = ev.dtend.value

            when = ""
            if start is not None and end is not None:
                when = f"{_fmt_dt(start)} → {_fmt_dt(end)}"
            elif start is not None:
                when = f"Starts: {_fmt_dt(start)}"
            elif end is not None:
                when = f"Ends: {_fmt_dt(end)}"
            else:
                when = "(no time)"

            attendees: list[str] = []
            if hasattr(ev, "attendee"):
                att = ev.attendee
                if isinstance(att, list):
                    props = att
                else:
                    props = [att]

                for a in props:
                    if hasattr(a, "value") and a.value:
                        attendees.append(str(a.value))

            lines.append(f"- {title}")
            lines.append(f"  UID: {uid}")
            lines.append(f"  When: {when}")
            if desc:
                lines.append(f"  Description: {desc}")
            if attendees:
                lines.append("  Attendees:")
                for a in attendees:
                    lines.append(f"    - {a}")
            lines.append("")  # blank line between events

        if not lines:
            return "No events."

        # Trim trailing blank line
        if lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def get(self, uid: str) -> CalendarObjectResource | None:
        """
        Find a single VEVENT by its iCal UID.
        Returns the first match, or None if not found.
        """
        # CalDAV search can filter by UID in many servers; if not supported,
        # we fall back to scanning recent items.
        try:
            results = self.calendar.search(uid=uid, event=True)
            if results:
                return results[0]
        except TypeError:
            # Some caldav backends don't accept uid=... in search()
            pass

        # Fallback: scan a reasonable window and match UID client-side
        for item in self.list():
            v = item.vobject_instance
            if not hasattr(v, "vevent"):
                continue
            ev = v.vevent
            if hasattr(ev, "uid") and getattr(ev.uid, "value", None) == uid:
                return item

        return None