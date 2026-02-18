import uuid
from urllib.parse import urljoin, urlparse

import requests
import vobject
from vobject.vcard import Name, Address
from xml.etree import ElementTree as ET


class ContactManager:
    def __init__(self, addressbook_url: str, username: str, password: str):
        # Make sure it ends with /
        if not addressbook_url.endswith("/"):
            addressbook_url += "/"
        self.base = addressbook_url
        self.auth = (username, password)

    def _req(self, method: str, url: str, **kwargs):
        return requests.request(method, url, auth=self.auth, timeout=20, **kwargs)

    def list(self):
        # Minimal PROPFIND asking for getetag; main goal is to get <href> entries
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

        # Parse DAV multistatus
        root = ET.fromstring(r.text)
        ns = {"d": "DAV:"}

        hrefs = []
        base_path = urlparse(self.base).path.rstrip("/") + "/"

        for resp in root.findall(".//d:response", ns):
            href_el = resp.find("d:href", ns)
            if href_el is None or not href_el.text:
                continue

            href_text = href_el.text
            # href in responses may be path-only; normalize to absolute
            abs_url = urljoin(self.base, href_text)

            # Skip the collection itself
            if urlparse(abs_url).path.rstrip("/") + "/" == base_path:
                continue

            if abs_url.lower().endswith(".vcf"):
                hrefs.append(abs_url)

        return hrefs

    def _vcard_escape(self, s: str) -> str:
        # vCard text escaping: \, ;, , and newlines
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(";", r"\;")
            .replace(",", r"\,")
        )

    def _build_vcard_text(self, *, name: str, email=None, phone=None, address=None, uid=None, version="3.0") -> str:
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

        if email:
            lines.append(f"EMAIL;TYPE=INTERNET:{self._vcard_escape(email)}")

        if phone:
            lines.append(f"TEL;TYPE=CELL:{self._vcard_escape(phone)}")

        if address:
            # ADR: POBOX;EXT;STREET;CITY;REGION;POSTAL;COUNTRY
            lines.append(f"ADR;TYPE=HOME:;;{self._vcard_escape(address)};;;;")

        lines.append("END:VCARD")

        # CRLF + final newline (important for picky servers)
        return "\r\n".join(lines) + "\r\n"

    def add(self, *, name: str, email=None, phone=None, address=None):
        filename = f"{uuid.uuid4()}.vcf"
        url = urljoin(self.base, filename)

        payload = self._build_vcard_text(name=name, email=email, phone=phone, address=address)
        print(f"{payload=}")
        r = self._req(
            "PUT",
            url,
            headers={
                "Content-Type": "text/vcard; charset=utf-8",
                "If-None-Match": "*",  # create-only, don't overwrite if exists
            },
            data=payload.encode("utf-8"),
        )
        r.raise_for_status()
        return url

    def get(self, url: str):
        r = self._req("GET", url)
        r.raise_for_status()
        return vobject.readOne(r.text)

    def delete(self, url: str):
        r = self._req("DELETE", url)
        r.raise_for_status()

    def update(self, url: str, *, new_name=None, new_email=None, new_phone=None, new_address=None):
        v = self.get(url)

        if new_name is not None:
            if hasattr(v, "fn"):
                v.fn.value = new_name
            else:
                v.add("fn").value = new_name

            parts = new_name.split()
            given = parts[0] if parts else ""
            family = parts[-1] if len(parts) > 1 else (parts[0] if parts else "")
            if hasattr(v, "n"):
                v.n.value = Name(family=family, given=given)
            else:
                v.add("n").value = Name(family=family, given=given)

        if new_email is not None:
            if hasattr(v, "email"):
                v.email.value = new_email
            else:
                v.add("email").value = new_email

        if new_phone is not None:
            if hasattr(v, "tel"):
                v.tel.value = new_phone
            else:
                v.add("tel").value = new_phone

        if new_address is not None:
            adr_val = Address(
                box="",
                extended="",
                street=new_address,
                city="",
                region="",
                code="",
                country="",
            )
            if hasattr(v, "adr"):
                v.adr.value = adr_val
            else:
                v.add("adr").value = adr_val

        payload = v.serialize()
        r = self._req("PUT", url, headers={"Content-Type": "text/vcard; charset=utf-8"}, data=payload)
        r.raise_for_status()
        return url
