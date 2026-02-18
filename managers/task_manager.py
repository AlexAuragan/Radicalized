import caldav


class TaskManager:
    def __init__(self, url: str, username: str, password: str):
        self.client = caldav.DAVClient(url, username=username, password=password)
        self.calendar = self.client.calendar(url=url)

    def list(self):
        return self.calendar.search(todo=True)

    def add(self, title: str, priority: int = 5):
        return self.calendar.save_todo(summary=title, priority=priority)

    def delete(self, item):
        item.delete()

    def update(self, item, *, new_title=None, new_desc=None):
        v = item.vobject_instance
        if not hasattr(v, "vtodo"):
            raise ValueError("Not a VTODO")
        td = v.vtodo
        if new_title is not None:
            if hasattr(td, "summary"):
                td.summary.value = new_title
            else:
                td.add("summary").value = new_title
        if new_desc is not None:
            if hasattr(td, "description"):
                td.description.value = new_desc
            else:
                td.add("description").value = new_desc
        item.save()
        return item
