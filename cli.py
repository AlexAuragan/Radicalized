#!./.venv/bin/python
import os
import sys
import argparse
from datetime import datetime
from radicale_manager import RadicaleManager
from dotenv import load_dotenv

load_dotenv()


def get_env(var, default=None):
    val = os.getenv(var)
    if not val and default is None:
        print(f"Error: Environment variable {var} is not set.")
        sys.exit(1)
    return val or default


def main():
    # 1. Load Credentials
    user = get_env("RADICALE_USER")
    password = get_env("RADICALE_PASS")

    parser = argparse.ArgumentParser(
        description="Radicale CLI: Unified Manager for Calendar, Tasks, Journals, and Contacts.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Global Selection Arguments
    parser.add_argument("--url", help="Override the target URL entirely")
    parser.add_argument(
        "--addr", action="store_true", help="Use the Address Book URL (RADICALE_ADDR)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # --- COMMAND: LIST ---
    subparsers.add_parser("list", help="List all items in the selected collection")

    # --- COMMAND: ADD ---
    add_p = subparsers.add_parser("add", help="Add a new item")
    add_p.add_argument(
        "--type", choices=["event", "task", "journal", "contact"], required=True
    )
    add_p.add_argument("--title", required=True, help="Summary or Full Name")
    add_p.add_argument("--desc", help="Description or Email")
    add_p.add_argument("--start", help="Start time (YYYY-MM-DD HH:MM)")
    add_p.add_argument("--end", help="End time (YYYY-MM-DD HH:MM)")

    # --- COMMAND: UPDATE ---
    upd_p = subparsers.add_parser(
        "update", help="Update an item by searching its current title"
    )
    upd_p.add_argument(
        "--find", required=True, help="Existing title/name to search for"
    )
    upd_p.add_argument("--new-title", help="New Summary or Name")
    upd_p.add_argument("--new-desc", help="New Description or Email")

    # --- COMMAND: DELETE ---
    del_p = subparsers.add_parser("delete", help="Delete an item by its title")
    del_p.add_argument("--title", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    # 2. Logic to choose the correct URL
    if args.url:
        target_url = args.url
    elif args.addr or (args.command == "add" and args.type == "contact"):
        target_url = get_env("RADICALE_ADDR")
    else:
        target_url = get_env("RADICALE_CAL")

    mgr = RadicaleManager(target_url, user, password)

    try:
        if args.command == "list":
            items = mgr.list_all()
            print(f"{'TYPE':<12} | {'SUMMARY / NAME':<30}")
            print("-" * 50)
            for item in items:
                v = item.vobject_instance
                name = "Unnamed"
                if hasattr(v, "vevent"):
                    name = v.vevent.summary.value
                elif hasattr(v, "vtodo"):
                    name = v.vtodo.summary.value
                elif hasattr(v, "vjournal"):
                    name = v.vjournal.summary.value
                elif hasattr(v, "vcard"):
                    name = v.vcard.fn.value
                print(f"{type(item).__name__:<12} | {name:<30}")

        elif args.command == "add":
            if args.type == "event":
                s = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
                e = datetime.strptime(args.end, "%Y-%m-%d %H:%M")
                mgr.add_event(args.title, s, e)
            elif args.type == "task":
                mgr.add_task(args.title)
            elif args.type == "journal":
                mgr.add_journal(args.title, args.desc or "")
            elif args.type == "contact":
                mgr.add_contact(args.title, args.desc or "")
            print(f"Success: Added {args.type} '{args.title}'")

        elif args.command == "update":
            items = mgr.list_all()
            target = None
            for item in items:
                v = item.vobject_instance
                curr = ""
                if hasattr(v, "vevent"):
                    curr = v.vevent.summary.value
                elif hasattr(v, "vtodo"):
                    curr = v.vtodo.summary.value
                elif hasattr(v, "vjournal"):
                    curr = v.vjournal.summary.value
                elif hasattr(v, "vcard"):
                    curr = v.vcard.fn.value
                if curr == args.find:
                    target = item
                    break

            if target:
                upd = {}
                is_vc = hasattr(target.vobject_instance, "vcard")
                if args.new_title:
                    upd["fn" if is_vc else "summary"] = args.new_title
                if args.new_desc:
                    upd["email" if is_vc else "description"] = args.new_desc
                mgr.update_item(target, upd)
                print(f"Success: Updated '{args.find}'")
            else:
                print(f"Error: Could not find '{args.find}'")

        elif args.command == "delete":
            # Finding logic for delete is similar to update
            items = mgr.list_all()
            for item in items:
                v = item.vobject_instance
                curr = ""
                if hasattr(v, "vevent"):
                    curr = v.vevent.summary.value
                elif hasattr(v, "vtodo"):
                    curr = v.vtodo.summary.value
                elif hasattr(v, "vjournal"):
                    curr = v.vjournal.summary.value
                elif hasattr(v, "vcard"):
                    curr = v.vcard.fn.value
                if curr == args.title:
                    mgr.delete_item(item)
                    print(f"Success: Deleted '{args.title}'")
                    return
            print(f"Error: '{args.title}' not found.")

    except Exception as e:
        print(f"Operation failed: {e}")


if __name__ == "__main__":
    main()
