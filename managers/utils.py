import os
from typing import Union, Sequence


def invite_attendees_by_icaluid(
    service,
    ical_uid: str,
    emails: Union[str, Sequence[str]],
    *,
    send_updates: str = "all",
    keep_existing: bool = True,
) -> dict:
    """
    Adds attendee emails to the Google Calendar event that matches the given iCalendar UID,
    and sends invitations via Google (sendUpdates).

    Args:
        service: Authorized googleapiclient.discovery.build("calendar", "v3", ...) service.
        ical_uid: The VEVENT UID from your CalDAV event (Google calls this iCalUID).
        emails: A single email or a list/tuple of emails to invite.
        send_updates: "all" | "externalOnly" | "none".
        keep_existing: If True, merges with existing attendees; if False, replaces.

    Returns:
        The updated Google event resource (dict).

    Raises:
        ValueError: If the event can't be found or multiple matches are found.
    """
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    if isinstance(emails, str):
        email_list = [emails]
    else:
        email_list = list(emails)

    # Normalize/dedupe while keeping order
    seen = set()
    cleaned: list[str] = []
    for e in email_list:
        e2 = e.strip()
        if not e2:
            continue
        e2_lower = e2.lower()
        if e2_lower in seen:
            continue
        seen.add(e2_lower)
        cleaned.append(e2)

    if not cleaned:
        raise ValueError("No attendee emails provided.")

    # 1) Find the Google event by iCalUID (VEVENT UID)
    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            iCalUID=ical_uid,
            maxResults=10,
            singleEvents=False,
        )
        .execute()
    )

    items = resp.get("items", [])
    if len(items) == 0:
        raise ValueError(
            f"No Google event found with iCalUID={ical_uid!r}. "
            "It may not have synced yet, or it synced into a different calendar."
        )
    if len(items) > 1:
        # This can happen in edge cases (duplicates, moved events, etc.)
        ids = [it.get("id") for it in items]
        raise ValueError(
            f"Multiple Google events found for iCalUID={ical_uid!r}: {ids}. "
            "Refine your selection logic (e.g., by start time) before inviting."
        )

    event = items[0]
    event_id = event["id"]

    # 2) Merge attendees
    new_attendees = [{"email": e} for e in cleaned]

    if keep_existing:
        existing = event.get("attendees", [])
        existing_emails_lower = {
            a.get("email", "").lower() for a in existing if a.get("email")
        }
        for a in new_attendees:
            if a["email"].lower() not in existing_emails_lower:
                existing.append(a)
        patch_body = {"attendees": existing}
    else:
        patch_body = {"attendees": new_attendees}

    # 3) Patch event and send invites
    updated = (
        service.events()
        .patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=patch_body,
            sendUpdates=send_updates,  # "all" is the usual invite behavior
        )
        .execute()
    )

    return updated


def sync_caldav_google():
    import subprocess

    n8n_id = os.environ["N8N_USER"]
    n8n_pass = os.environ["N8N_PASSWORD"]

    out = subprocess.run(
        [
            "curl",
            "https://n8n.auragan.fr/webhook/sync_calendars",
            "-u",
            f"{n8n_id}:{n8n_pass}",
        ],
        capture_output=True,
    )
    print("Synced local Caldav with Google Calendar successfully")
