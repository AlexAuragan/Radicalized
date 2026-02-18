import hashlib
import json
import os
import sys
from pathlib import Path

import requests
import vobject

from managers.calendar_manager import CalendarManager
from managers.contact_manager import ContactManager
from managers.journal_manager import JournalManager
from managers.task_manager import TaskManager


def get_env(var, default=None):
    val = os.getenv(var)
    if not val and default is None:
        print(f"Error: Environment variable {var} is not set.")
        sys.exit(1)
    return val or default

def extract_vobject(raw, user: str, password: str):
    """
    Return a vobject instance if available.
    If tuple is (url, props, None), fetch+cache URL and parse into vobject.
    """
    if hasattr(raw, "vobject_instance"):
        return raw.vobject_instance

    if isinstance(raw, tuple):
        # Common pattern: (url, props, data)
        if len(raw) >= 3 and raw[2] is not None:
            return raw[2]

        if len(raw) >= 1:
            url = str(raw[0])
            return vobject_from_url(url, user, password)

    return None



def extract_href(raw):
    """
    Best-effort identifier for printing / fallback:
      - for tuples: first element is usually the URL/href
      - for objects: str(raw.url) sometimes exists, else repr(raw)
    """
    if isinstance(raw, tuple) and len(raw) >= 1:
        return str(raw[0])
    if hasattr(raw, "url"):
        return str(raw.url)
    return repr(raw)



def extract_display_name(vobj):
    """
    Pull a human label from a vobject instance (event/task/journal/vcard).
    Works with both:
      - top-level VCARD (vobj.fn)
      - VCALENDAR with vevent/vtodo/vjournal (vobj.vevent / vobj.vtodo / vobj.vjournal)
      - nested shapes (rare) where vobj.vcard exists
    """
    if vobj is None:
        return None

    # VCARD usually comes back as top-level object with .fn
    if hasattr(vobj, "fn"):
        try:
            return vobj.fn.value
        except Exception:
            pass

    # Sometimes people wrap it (depends on caller)
    if hasattr(vobj, "vcard") and hasattr(vobj.vcard, "fn"):
        try:
            return vobj.vcard.fn.value
        except Exception:
            pass

    # VCALENDAR objects
    if hasattr(vobj, "vevent") and hasattr(vobj.vevent, "summary"):
        return vobj.vevent.summary.value
    if hasattr(vobj, "vtodo") and hasattr(vobj.vtodo, "summary"):
        return vobj.vtodo.summary.value
    if hasattr(vobj, "vjournal") and hasattr(vobj.vjournal, "summary"):
        return vobj.vjournal.summary.value

    return None


def cache_dir() -> Path:
    d = str(Path.home() / ".cache" / "radicale-cli")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_paths(url: str):
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    ext = ".vcf" if url.lower().endswith(".vcf") else ".ics"
    base = cache_dir() / h
    return base.with_suffix(ext), base.with_suffix(".json")


def load_cached(meta_path: Path):
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_and_cache(url: str, user: str, password: str) -> str:
    """
    Returns the item text (VCF/ICS), using cache when possible.
    """
    data_path, meta_path = cache_paths(url)
    meta = load_cached(meta_path)

    headers = {}
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    r = requests.get(url, auth=(user, password), headers=headers, timeout=15)

    if r.status_code == 304 and data_path.exists():
        return data_path.read_text(encoding="utf-8", errors="replace")

    r.raise_for_status()
    text = r.text

    data_path.write_text(text, encoding="utf-8")
    new_meta = {
        "url": url,
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
    }
    meta_path.write_text(json.dumps(new_meta, indent=2), encoding="utf-8")

    return text


def vobject_from_url(url: str, user: str, password: str):
    text = fetch_and_cache(url, user, password)
    # vobject.readOne handles VCARD and VCALENDAR
    return vobject.readOne(text)


# ----------------------------
# Finder helpers (by title/name)
# ----------------------------
def find_caldav_item_by_title(items, wanted: str):
    for item in items:
        v = item.vobject_instance
        name = extract_display_name(v) or ""
        if name == wanted:
            return item
    return None


def find_contact_url_by_name(cm: ContactManager, wanted: str):
    # list() returns URLs; get(url) returns vobject vCard
    for url in cm.list():
        try:
            v = cm.get(url)
        except Exception:
            continue
        name = extract_display_name(v) or ""
        if name == wanted:
            return url
    return None


# ----------------------------
# Manager selection
# ----------------------------
def get_manager(kind: str, *, cal_url: str, addr_url: str, user: str, password: str):
    if kind == "event":
        return CalendarManager(cal_url, user, password)
    if kind == "task":
        return TaskManager(cal_url, user, password)
    if kind == "journal":
        return JournalManager(cal_url, user, password)
    if kind == "contact":
        return ContactManager(addr_url, user, password)
    raise ValueError(f"Unknown kind: {kind}")

def vcard_values(v, key: str):
    """
    Return a list of values for a vCard property (email/tel/adr/etc.)
    Uses v.contents to handle repeated fields properly.
    """
    if v is None:
        return []
    lines = v.contents.get(key, [])
    out = []
    for line in lines:
        try:
            out.append(line.value)
        except Exception:
            # some vobject lines can be weird; ignore silently
            pass
    return out


def format_contact_extra(v):
    emails = vcard_values(v, "email")
    tels = vcard_values(v, "tel")
    adrs = vcard_values(v, "adr")

    parts = []

    if emails:
        # display one (or join if you prefer)
        parts.append(f"<{emails[0]}>")

    if tels:
        parts.append(f"tel:{tels[0]}")

    if adrs:
        # adr value is usually an Address object; put something readable
        adr = adrs[0]
        try:
            # vobject Address has fields like street/city/code/country
            adr_parts = [adr.street, adr.city, adr.code, adr.country]
            adr_str = ", ".join([p for p in adr_parts if p])
        except Exception:
            adr_str = str(adr)

        if adr_str:
            parts.append(adr_str)

    return (" " + " | ".join(parts)) if parts else ""
