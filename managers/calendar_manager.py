import os
from datetime import datetime
from typing import Sequence, Union

import caldav
import vobject

from managers.utils import invite_attendees_by_icaluid, sync_caldav_google


class CalendarManager:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        *,
        google_service,
        google_calendar_id_env: str = "GOOGLE_CALENDAR_ID",
    ):
        self.client = caldav.DAVClient(url, username=username, password=password)
        self.calendar = self.client.calendar(url=url)

        self.google_service = google_service
        self.google_calendar_id = os.environ[google_calendar_id_env]

    def list(self):
        # Returns CalendarObjectResource list
        return self.calendar.search(event=True)

    def add(self, title: str, start: datetime, end: datetime):
        return self.calendar.save_event(dtstart=start, dtend=end, summary=title)

    def delete(self, item):
        item.delete()

    def update(self, item, *, new_title=None, new_desc=None):
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
        Invite attendees by using Google Calendar as the scheduling/invite engine.

        This takes the VEVENT UID from the CalDAV item, finds the corresponding
        Google event via iCalUID, and patches attendees with sendUpdates so
        Google emails invitations.

        Note: the item must have already been synced to Google for this to work.
        """
        try:
            sync_caldav_google()
        except Exception as e:
            print("Sync between CalDAV and Google Calendar failed, ignoring")
        v = item.vobject_instance
        if not hasattr(v, "vevent"):
            raise ValueError("Not a VEVENT")

        ev = v.vevent
        if not hasattr(ev, "uid") or not getattr(ev.uid, "value", None):
            raise ValueError("VEVENT has no UID; cannot invite by iCalUID.")

        ical_uid = ev.uid.value

        return invite_attendees_by_icaluid(
            self.google_service,
            ical_uid,
            emails,
            send_updates=send_updates,
            keep_existing=keep_existing,
        )
