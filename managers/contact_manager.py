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

    def _build_vcard_text(
            self,
            *,
            name: str,
            email=None,
            phone=None,
            address=None,
            org=None,
            title=None,
            birthday=None,
            note=None,
            website=None,
            instagram=None,
            linkedin=None,
            github=None,
            uid=None,
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

    def add(
            self,
            *,
            name: str,
            email=None,
            phone=None,
            address=None,
            org=None,
            title=None,
            birthday=None,
            note=None,
            website=None,
            instagram=None,
            linkedin=None,
            github=None,
            twitter=None,
    ):
        filename = f"{uuid.uuid4()}.vcf"
        url = urljoin(self.base, filename)

        payload = self._build_vcard_text(
            name=name,
            email=email,
            phone=phone,
            address=address,
            org=org,
            title=title,
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
        return url
    def get(self, url: str):
        r = self._req("GET", url)
        r.raise_for_status()
        return vobject.readOne(r.text)

    def delete(self, url: str):
        r = self._req("DELETE", url)
        r.raise_for_status()

    def update(
            self,
            url: str,
            *,
            new_name=None,
            new_email=None,
            new_phone=None,
            new_address=None,
            new_org=None,
            new_title=None,
            new_birthday=None,
            new_note=None,
            new_website=None,
            new_instagram=None,
            new_linkedin=None,
            new_github=None,
            new_twitter=None,
    ):

        v = self.get(url)

        # identité
        if new_name is not None:
            self._set_or_add_single(v, "fn", new_name)

            parts = new_name.split()
            given = parts[0] if parts else ""
            family = parts[-1] if len(parts) > 1 else ""
            self._set_or_add_single(v, "n", f"{family};{given};;;")

        if new_org is not None:
            self._set_or_add_single(v, "org", new_org)
        if new_title is not None:
            self._set_or_add_single(v, "title", new_title)

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
            ig = self._normalize_handle_url(new_instagram, "https://instagram.com", at_ok=True)
            self._set_social(v, "instagram", ig)

        if new_linkedin is not None:
            li = self._normalize_handle_url(new_linkedin, "https://linkedin.com/in", at_ok=False)
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
        return url

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
            if hasattr(line, "params") and "TYPE" in line.params and len(line.params["TYPE"]) > 0:
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
