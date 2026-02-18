
import caldav


class JournalManager:
    def __init__(self, url: str, username: str, password: str):
        self.client = caldav.DAVClient(url, username=username, password=password)
        self.calendar = self.client.calendar(url=url)

    def list(self):
        return self.calendar.search(journal=True)

    def add(self, title: str, desc: str = ""):
        return self.calendar.save_journal(summary=title, description=desc)

    def delete(self, item):
        item.delete()

    def update(self, item, *, new_title=None, new_desc=None):
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
