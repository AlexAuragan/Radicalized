#!/home/moltbot/clawd/skills/radicale/scripts/Radicalized/.venv/bin/python
import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv

from utils import (
    find_caldav_item_by_title,
    find_contact_url_by_name,
    extract_display_name,
    get_manager,
    get_env,
    format_contact_extra,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Radicale CLI (CalDAV + CardDAV)",
    )

    top = parser.add_subparsers(dest="kind", required=True)

    # For each resource type
    for kind in ["event", "task", "journal", "contact"]:
        kind_parser = top.add_parser(kind)
        kind_parser.set_defaults(_kind_parser=kind_parser)
        actions = kind_parser.add_subparsers(dest="action", required=False)

        # LIST
        actions.add_parser("list")

        # ADD
        add = actions.add_parser("add")

        if kind == "event":
            add.add_argument("--title", required=True)
            add.add_argument("--start", required=True, help="YYYY-MM-DD HH:MM")
            add.add_argument("--end", required=True, help="YYYY-MM-DD HH:MM")
            add.add_argument(
                "--invite",
                nargs="+",
                help="One or more attendee emails to invite via Google Calendar API",
            )

        elif kind == "task":
            add.add_argument("--title", required=True)
            add.add_argument("--priority", type=int, default=5)
            add.add_argument("--desc")
            add.add_argument("--due", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
            add.add_argument("--start", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
            add.add_argument(
                "--status", help="NEEDS-ACTION | IN-PROCESS | COMPLETED | CANCELLED"
            )
            add.add_argument("--percent-complete", type=int, dest="percent_complete")
            add.add_argument(
                "--categories", nargs="+", help="One or more category strings"
            )
            add.add_argument("--location")
            add.add_argument("--url")

        elif kind == "journal":
            add.add_argument("--title", required=True)
            add.add_argument("--desc", default="")

        elif kind == "contact":
            add.add_argument("--name", required=True)
            add.add_argument("--email")
            add.add_argument("--phone")
            add.add_argument("--address")
            add.add_argument("--org", help="Organization or company name (vCard ORG)")

            g_social = add.add_argument_group("Social networks")
            g_social.add_argument("--website")
            g_social.add_argument("--instagram", help="@handle or URL")
            g_social.add_argument("--linkedin", help="URL")
            g_social.add_argument("--github", help="handle or URL")

            g_misc = add.add_argument_group("Other")
            g_misc.add_argument("--birthday", help="YYYY-MM-DD")
            g_misc.add_argument("--note", help="Any note")

        # UPDATE
        update = actions.add_parser("update")
        update.add_argument("--find", required=True)

        if kind == "event":
            update.add_argument("--new-title")
            update.add_argument("--new-desc")
            update.add_argument(
                "--invite",
                nargs="+",
                help="One or more attendee emails to invite via Google Calendar API",
            )
        elif kind == "contact":
            g_id = update.add_argument_group("Identity")
            g_id.add_argument("--new-name")
            g_id.add_argument("--new-org")

            g_contact = update.add_argument_group("Contact")
            g_contact.add_argument("--new-email")
            g_contact.add_argument("--new-phone")
            g_contact.add_argument("--new-address")

            g_social = update.add_argument_group("Social networks")
            g_social.add_argument("--new-website")
            g_social.add_argument("--new-instagram")
            g_social.add_argument("--new-linkedin")
            g_social.add_argument("--new-github")

            g_misc = update.add_argument_group("Other")
            g_misc.add_argument("--new-birthday")
            g_misc.add_argument("--new-note")
        elif kind == "task":
            update.add_argument("--new-title")
            update.add_argument("--new-desc")
            update.add_argument("--new-priority", type=int, dest="new_priority")
            update.add_argument(
                "--new-due", dest="new_due", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
            )
            update.add_argument(
                "--new-start",
                dest="new_start",
                help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
            )
            update.add_argument(
                "--new-status",
                dest="new_status",
                help="NEEDS-ACTION | IN-PROCESS | COMPLETED | CANCELLED",
            )
            update.add_argument(
                "--new-percent-complete", type=int, dest="new_percent_complete"
            )
            update.add_argument("--new-categories", nargs="+", dest="new_categories")
            update.add_argument("--new-location", dest="new_location")
            update.add_argument("--new-url", dest="new_url")
        else:
            update.add_argument("--new-title")
            update.add_argument("--new-desc")

        # DELETE
        delete = actions.add_parser("delete")
        delete.add_argument("--find", required=True)

    return parser


def main():
    user = get_env("RADICALE_USER")
    password = get_env("RADICALE_PASS")

    parser = build_parser()
    args = parser.parse_args()

    if not args.action:
        args._kind_parser.print_help()
        sys.exit(0)

    cal_url = get_env("RADICALE_CAL")
    addr_url = get_env("RADICALE_ADDR")
    mgr = get_manager(
        args.kind, cal_url=cal_url, addr_url=addr_url, user=user, password=password
    )

    try:
        # ---------------- LIST ----------------
        if args.action == "list":
            print(f"{'TYPE':<10} | SUMMARY / NAME")
            print("-" * 50)

            if args.kind == "contact":
                for url in mgr.list():
                    v = mgr.get(url)
                    name = extract_display_name(v) or "Unnamed"
                    extra = format_contact_extra(v)
                    print(f"{'contact':<10} | {name}{extra}")
            else:
                for item in mgr.list():
                    name = extract_display_name(item.vobject_instance) or "Unnamed"
                    print(f"{args.kind:<10} | {name}")

        # ---------------- ADD ----------------
        elif args.action == "add":
            if args.kind == "event":
                s = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
                e = datetime.strptime(args.end, "%Y-%m-%d %H:%M")
                created = mgr.add(args.title, s, e)

                if args.invite:
                    mgr.invite(created, args.invite)

            elif args.kind == "task":
                mgr.add(
                    args.title,
                    priority=args.priority,
                    description=args.desc,
                    due=args.due,
                    start=args.start,
                    status=args.status,
                    percent_complete=args.percent_complete,
                    categories=args.categories,
                    location=args.location,
                    url=args.url,
                )

            elif args.kind == "journal":
                mgr.add(args.title, desc=args.desc)

            elif args.kind == "contact":
                mgr.add(
                    name=args.name,
                    email=args.email,
                    phone=args.phone,
                    address=args.address,
                    org=args.org,
                    birthday=args.birthday,
                    note=args.note,
                    website=args.website,
                    instagram=args.instagram,
                    linkedin=args.linkedin,
                    github=args.github,
                )

            print("Success")

        # ---------------- UPDATE ----------------
        elif args.action == "update":
            if args.kind == "contact":
                url = find_contact_url_by_name(mgr, args.find)
                if not url:
                    print("Not found")
                    sys.exit(1)

                mgr.update(
                    url,
                    new_name=args.new_name,
                    new_email=args.new_email,
                    new_phone=args.new_phone,
                    new_address=args.new_address,
                    new_org=args.new_org,
                    new_birthday=args.new_birthday,
                    new_note=args.new_note,
                    new_website=args.new_website,
                    new_instagram=args.new_instagram,
                    new_linkedin=args.new_linkedin,
                    new_github=args.new_github,
                )
            else:
                items = mgr.list()
                target = find_caldav_item_by_title(items, args.find)
                if not target:
                    print("Not found")
                    sys.exit(1)

                if args.kind == "task":
                    mgr.update(
                        target,
                        new_title=args.new_title,
                        new_description=args.new_desc,
                        new_priority=args.new_priority,
                        new_due=args.new_due,
                        new_start=args.new_start,
                        new_status=args.new_status,
                        new_percent_complete=args.new_percent_complete,
                        new_categories=args.new_categories,
                        new_location=args.new_location,
                        new_url=args.new_url,
                    )
                else:
                    mgr.update(
                        target,
                        new_title=args.new_title,
                        new_desc=args.new_desc,
                    )

                    if args.kind == "event" and args.invite:
                        mgr.invite(target, args.invite)

            print("Success")

        # ---------------- DELETE ----------------
        elif args.action == "delete":
            if args.kind == "contact":
                url = find_contact_url_by_name(mgr, args.find)
                if not url:
                    print("Not found")
                    sys.exit(1)
                mgr.delete(url)
            else:
                items = mgr.list()
                target = find_caldav_item_by_title(items, args.find)
                if not target:
                    print("Not found")
                    sys.exit(1)
                mgr.delete(target)

            print("Success")

    except Exception as e:
        print(f"Operation failed: {e}")
        raise e
        sys.exit(1)


if __name__ == "__main__":
    load_dotenv()
    main()
