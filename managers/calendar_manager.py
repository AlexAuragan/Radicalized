import caldav
import vobject
from datetime import datetime


class CalendarManager:
    def __init__(self, url: str, username: str, password: str):
        self.client = caldav.DAVClient(url, username=username, password=password)
        self.calendar = self.client.calendar(url=url)

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
