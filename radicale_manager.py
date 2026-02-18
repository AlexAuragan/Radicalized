import caldav
from vobject import vCard
from vobject.vcard import Name, Address


class RadicaleManager:
    def __init__(self, url, username, password):
        self.client = caldav.DAVClient(url, username=username, password=password)
        # This points the client specifically to the collection URL provided
        self.collection = self.client.calendar(url=url)

    # --- CALENDAR, TASKS, & JOURNALS (iCal) ---
    def add_event(self, summary, start, end):
        """Standard Calendar Event"""
        return self.collection.save_event(dtstart=start, dtend=end, summary=summary)

    def add_task(self, summary, priority=5):
        """VTODO item for your Tasks list"""
        return self.collection.save_todo(summary=summary, priority=priority)

    def add_journal(self, summary, description):
        """VJOURNAL item for your Journal"""
        return self.collection.save_journal(summary=summary, description=description)

    # --- ADDRESS BOOK (vCard) ---
    def add_contact(self, name, email=None, phone=None, address=None):
        """Adds a CardDAV contact"""
        vcard = vCard()

        # FN
        vcard.add("fn").value = name

        # N (best-effort split)
        parts = name.split()
        given = parts[0] if parts else ""
        family = parts[-1] if len(parts) > 1 else (parts[0] if parts else "")

        vcard.add("n").value = Name(family=family, given=given)

        # EMAIL (optional)
        if email:
            vcard.add("email").value = email

        # TEL (optional)
        if phone:
            vcard.add("tel").value = phone

        # ADR (optional)
        if address:
            vcard.add("adr").value = Address(
                box="",
                extended="",
                street=address,  # free-form string goes here
                city="",
                region="",
                code="",
                country="",
            )

        return self.collection.save_vcard(vcard.serialize())

    # --- GENERAL UTILITIES ---
    def list_all(self):
        """Lists everything in this specific collection"""
        return self.collection.children()

    def delete_item(self, item):
        """Deletes any object (Event, Task, or Contact)"""
        item.delete()

    def update_item(self, item, updates):
        """
        Generic update method.
        'item' is the object returned by list_all() or add_ methods.
        'updates' is a dictionary: {'summary': 'New Title', 'description': 'New Bio'}
        """
        # Get the component (vevent, vtodo, vjournal, or vcard)
        # iCal objects use 'instance.vevent', Contacts use 'instance.vcard'
        if hasattr(item.vobject_instance, "vevent"):
            comp = item.vobject_instance.vevent
        elif hasattr(item.vobject_instance, "vtodo"):
            comp = item.vobject_instance.vtodo
        elif hasattr(item.vobject_instance, "vjournal"):
            comp = item.vobject_instance.vjournal
        elif hasattr(item.vobject_instance, "vcard"):
            comp = item.vobject_instance.vcard
        else:
            raise ValueError("Unknown item type")

        # Apply updates dynamically
        for key, value in updates.items():
            if hasattr(comp, key):
                getattr(comp, key).value = value
            else:
                comp.add(key).value = value

        item.save()
        return item
