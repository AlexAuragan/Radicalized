import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
import vobject
from xml.etree import ElementTree as ET

from managers.manager import Manager


@dataclass(frozen=True)
class Contact:
    url: str
    uid: str
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    org: str = ""
    title: str = ""
    birthday: str = ""
    note: str = ""
    website: str = ""

    def serialize(self):
        return str(self)


class ContactManager(Manager[Contact]):
    def __init__(self, addressbook_url: str, username: str, password: str):
        super().__init__(addressbook_url, username, password)
        self.calendar = self.client.calendar(url=addressbook_url)

    def _req(self, method: str, url: str, **kwargs):
        return requests.request(method, url, auth=self.auth, timeout=20, **kwargs)

    # ----------------------------
    # Listing
    # ----------------------------

    def list_urls(self) -> list[str]:
        """
        Cheap listing: returns .vcf URLs without downloading each vCard.
        """
        body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:getetag/></d:prop>
</d:propfind>
"""
        r = self._req(
            "PROPFIND",
            self.base,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=body,
        )
        r.raise_for_status()

        root = ET.fromstring(r.text)
        ns = {"d": "DAV:"}

        hrefs: list[str] = []
        base_path = urlparse(self.base).path.rstrip("/") + "/"

        for resp in root.findall(".//d:response", ns):
            href_el = resp.find("d:href", ns)
            if href_el is None or not href_el.text:
                continue

            href_text = href_el.text
            abs_url = urljoin(self.base, href_text)

            # Skip the collection itself
            if urlparse(abs_url).path.rstrip("/") + "/" == base_path:
                continue

            if abs_url.lower().endswith(".vcf"):
                hrefs.append(abs_url)

        return hrefs

    def list(self, limit: int = 200) -> list[Contact]:
        """
        Object listing: fetches up to `limit` vCards and returns Contact objects.
        """
        urls = self.list_urls()[:limit]
        out: list[Contact] = []

        for url in urls:
            try:
                v = self.request(url)
            except Exception:
                continue
            out.append(self._contact_from_vobject(url, v))

        return out

    # ----------------------------
    # vCard building / parsing
    # ----------------------------

    def _vcard_escape(self, s: str) -> str:
        # vCard text escaping: \, ;, , and newlines
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(";", r"\;")
            .replace(",", r"\,")
        )

    def _build_vcard_text(
        self,
        *,
        name: str,
        email: str = None,
        phone: str = None,
        address: str = None,
        org: str = None,
        title: str = None,
        birthday: str = None,
        note: str = None,
        website: str = None,
        instagram: str = None,
        linkedin: str = None,
        github: str = None,
        uid: str = None,
        version="3.0",
    ) -> str:
        uid = uid or str(uuid.uuid4())

        parts = name.split()
        given = parts[0] if parts else ""
        family = parts[-1] if len(parts) > 1 else ""

        lines = [
            "BEGIN:VCARD",
            f"VERSION:{version}",
            f"UID:{self._vcard_escape(uid)}",
            f"FN:{self._vcard_escape(name)}",
            f"N:{self._vcard_escape(family)};{self._vcard_escape(given)};;;",
        ]

        if org:
            lines.append(f"ORG:{self._vcard_escape(org)}")
        if title:
            lines.append(f"TITLE:{self._vcard_escape(title)}")

        if email:
            lines.append(f"EMAIL;TYPE=INTERNET:{self._vcard_escape(email)}")
        if phone:
            lines.append(f"TEL;TYPE=CELL:{self._vcard_escape(phone)}")
        if address:
            lines.append(f"ADR;TYPE=HOME:;;{self._vcard_escape(address)};;;;")

        if birthday:
            # vCard 3.0: BDAY:YYYY-MM-DD (généralement accepté)
            lines.append(f"BDAY:{self._vcard_escape(birthday)}")

        if note:
            lines.append(f"NOTE:{self._vcard_escape(note)}")

        # Liens / réseaux
        if website:
            lines.append(f"URL:{self._vcard_escape(website)}")

        def add_social(social_type: str, value: str, base: str, at_ok=True):
            if not value:
                return
            url = self._normalize_handle_url(value, base=base, at_ok=at_ok)
            lines.append(f"X-SOCIALPROFILE;TYPE={social_type}:{self._vcard_escape(url)}")

        add_social("instagram", instagram, "https://instagram.com", at_ok=True)
        add_social("linkedin", linkedin, "https://linkedin.com/in", at_ok=False)
        add_social("github", github, "https://github.com", at_ok=False)

        lines.append("END:VCARD")
        return "\r\n".join(lines) + "\r\n"

    def _contact_from_vobject(self, url: str, v) -> Contact:
        def first_value(key: str) -> str:
            if key in v.contents and v.contents[key]:
                val = v.contents[key][0].value
                return "" if val is None else str(val).strip()
            return ""

        uid = first_value("uid")
        name = first_value("fn")
        email = first_value("email")
        phone = first_value("tel")
        org = first_value("org")
        title = first_value("title")
        birthday = first_value("bday")
        note = first_value("note")
        website = first_value("url")

        address = ""
        if "adr" in v.contents and v.contents["adr"]:
            adr_val = v.contents["adr"][0].value
            address = "" if adr_val is None else str(adr_val).strip()

        return Contact(
            url=url,
            uid=uid,
            name=name,
            email=email,
            phone=phone,
            address=address,
            org=org,
            title=title,
            birthday=birthday,
            note=note,
            website=website,
        )

    # ----------------------------
    # CRUD
    # ----------------------------

    def add(
        self,
        *,
        name: str,
        email=None,
        phone=None,
        address=None,
        org=None,
        birthday=None,
        note=None,
        website=None,
        instagram=None,
        linkedin=None,
        github=None,
    ) -> Contact:
        filename = f"{uuid.uuid4()}.vcf"
        url = urljoin(self.base, filename)

        payload = self._build_vcard_text(
            name=name,
            email=email,
            phone=phone,
            address=address,
            org=org,
            birthday=birthday,
            note=note,
            website=website,
            instagram=instagram,
            linkedin=linkedin,
            github=github,
        )

        r = self._req(
            "PUT",
            url,
            headers={
                "Content-Type": "text/vcard; charset=utf-8",
                "If-None-Match": "*",
            },
            data=payload.encode("utf-8"),
        )
        r.raise_for_status()

        v = self.request(url)
        return self._contact_from_vobject(url, v)

    def delete(self, item: Contact):
        r = self._req("DELETE", item.url)
        r.raise_for_status()

    def update(
        self,
        item: Contact,
        *,
        new_name=None,
        new_email=None,
        new_phone=None,
        new_address=None,
        new_org=None,
        new_birthday=None,
        new_note=None,
        new_website=None,
        new_instagram=None,
        new_linkedin=None,
        new_github=None,
        new_twitter=None,
    ) -> Contact:
        url = item.url
        v = self.request(url)

        # identité
        if new_name is not None:
            self._set_or_add_single(v, "fn", new_name)

            parts = new_name.split()
            given = parts[0] if parts else ""
            family = parts[-1] if len(parts) > 1 else ""
            self._set_or_add_single(v, "n", f"{family};{given};;;")

        if new_org is not None:
            self._set_or_add_single(v, "org", new_org)

        # contact
        if new_email is not None:
            self._set_or_add_single(v, "email", new_email)
        if new_phone is not None:
            self._set_or_add_single(v, "tel", new_phone)
        if new_address is not None:
            self._set_or_add_single(v, "adr", f";;{new_address};;;;")

        # autres
        if new_birthday is not None:
            self._set_or_add_single(v, "bday", new_birthday)
        if new_note is not None:
            self._set_or_add_single(v, "note", new_note)

        # liens / réseaux
        if new_website is not None:
            self._set_or_add_single(v, "url", new_website)

        if new_instagram is not None:
            ig = self._normalize_handle_url(
                new_instagram, "https://instagram.com", at_ok=True
            )
            self._set_social(v, "instagram", ig)

        if new_linkedin is not None:
            li = self._normalize_handle_url(
                new_linkedin, "https://linkedin.com/in", at_ok=False
            )
            self._set_social(v, "linkedin", li)

        if new_github is not None:
            gh = self._normalize_handle_url(new_github, "https://github.com", at_ok=False)
            self._set_social(v, "github", gh)

        if new_twitter is not None:
            tw = self._normalize_handle_url(new_twitter, "https://twitter.com", at_ok=True)
            self._set_social(v, "twitter", tw)

        payload = v.serialize()
        payload = payload.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        if not payload.endswith("\r\n"):
            payload += "\r\n"

        r = self._req(
            "PUT",
            url,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
            data=payload.encode("utf-8"),
        )
        r.raise_for_status()

        v2 = self.request(url)
        return self._contact_from_vobject(url, v2)

    # ----------------------------
    # Helpers for socials + vobject mutations
    # ----------------------------

    def _normalize_handle_url(self, value: str, base: str, at_ok=True) -> str:
        v = value.strip()
        if at_ok and v.startswith("@"):
            v = v[1:]
        if v.startswith("http://") or v.startswith("https://"):
            return v
        return f"{base.rstrip('/')}/{v}"

    def _set_or_add_single(self, v, key: str, value: str):
        # key en minuscule (email, tel, org, title, note, bday, url...)
        if value is None:
            return
        if key in v.contents and len(v.contents[key]) > 0:
            v.contents[key][0].value = value
        else:
            v.add(key).value = value

    def _remove_social_type(self, v, social_type: str):
        key = "x-socialprofile"
        if key not in v.contents:
            return
        kept = []
        for line in v.contents[key]:
            t = ""
            if "TYPE" in line.params and len(line.params["TYPE"]) > 0:
                t = line.params["TYPE"][0]
            if str(t).lower() != social_type.lower():
                kept.append(line)
        v.contents[key] = kept

    def _set_social(self, v, social_type: str, url: str):
        # remplace l’entrée existante de ce type
        self._remove_social_type(v, social_type)
        line = v.add("x-socialprofile")
        line.params["TYPE"] = [social_type]
        line.value = url

    # ----------------------------
    # Convenience methods
    # ----------------------------

    def summary(self, limit: int = 50) -> str:
        """
        Display a short list of contacts (FN + EMAIL/TEL if present).
        `limit` avoids hammering the server if you have lots of vcards.
        """
        contacts = self.list(limit=limit)

        lines: list[str] = []
        for c in contacts:
            label = c.name or "(no name)"
            bits = []
            if c.email:
                bits.append(c.email)
            if c.phone:
                bits.append(c.phone)

            if c.uid:
                lines.append(f"- {label} (UID: {c.uid})")
            else:
                lines.append(f"- {label}")

            if bits:
                lines.append("  " + " / ".join(bits))

        if not lines:
            return "No contacts."

        total_urls = len(self.list_urls())
        if len(contacts) < total_urls:
            lines.append(f"\n(showing first {limit})")

        return "\n".join(lines)

    def get(self, uid: str, *, limit: int = 200) -> Contact | None:
        """
        Find a contact by vCard UID. Returns the Contact object or None.

        `limit` avoids scanning your whole addressbook in huge collections.
        """
        urls = self.list_urls()[:limit]
        target = uid.strip()

        for url in urls:
            try:
                v = self.request(url)
            except Exception:
                continue

            if "uid" in v.contents and v.contents["uid"] and v.contents["uid"][0].value:
                v_uid = str(v.contents["uid"][0].value).strip()
                if v_uid == target:
                    return self._contact_from_vobject(url, v)

        return None