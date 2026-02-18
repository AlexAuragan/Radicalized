#!~/clawd/skills/radicale/scripts/Radicalized
import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv

from utils import find_caldav_item_by_title, find_contact_url_by_name, extract_display_name, get_manager, get_env, \
    format_contact_extra


def build_parser():
    parser = argparse.ArgumentParser(
        description="Radicale CLI (CalDAV + CardDAV)",
    )

    parser.add_argument("--url", help="Override CalDAV URL")
    parser.add_argument("--addr-url", help="Override CardDAV URL")

    top = parser.add_subparsers(dest="kind", required=True)

    # For each resource type
    for kind in ["event", "task", "journal", "contact"]:
        kind_parser = top.add_parser(kind)
        actions = kind_parser.add_subparsers(dest="action", required=True)

        # LIST
        actions.add_parser("list")

        # ADD
        add = actions.add_parser("add")

        if kind == "event":
            add.add_argument("--title", required=True)
            add.add_argument("--start", required=True, help="YYYY-MM-DD HH:MM")
            add.add_argument("--end", required=True, help="YYYY-MM-DD HH:MM")

        elif kind == "task":
            add.add_argument("--title", required=True)
            add.add_argument("--priority", type=int, default=5)

        elif kind == "journal":
            add.add_argument("--title", required=True)
            add.add_argument("--desc", default="")

        elif kind == "contact":
            add.add_argument("--name", required=True)
            add.add_argument("--email")
            add.add_argument("--phone")
            add.add_argument("--address")

        # UPDATE
        update = actions.add_parser("update")
        update.add_argument("--find", required=True)

        if kind == "contact":
            update.add_argument("--new-name")
            update.add_argument("--new-email")
            update.add_argument("--new-phone")
            update.add_argument("--new-address")
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

    cal_url = get_env("RADICALE_CAL")
    addr_url = get_env("RADICALE_ADDR")
    mgr = get_manager(args.kind, cal_url=cal_url, addr_url=addr_url, user=user, password=password)

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
                mgr.add(args.title, s, e)

            elif args.kind == "task":
                mgr.add(args.title, priority=args.priority)

            elif args.kind == "journal":
                mgr.add(args.title, desc=args.desc)

            elif args.kind == "contact":
                mgr.add(
                    name=args.name,
                    email=args.email,
                    phone=args.phone,
                    address=args.address,
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
                )
            else:
                items = mgr.list()
                target = find_caldav_item_by_title(items, args.find)
                if not target:
                    print("Not found")
                    sys.exit(1)

                mgr.update(
                    target,
                    new_title=args.new_title,
                    new_desc=args.new_desc,
                )

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
