"""
fetch_group_messages.py

Fetches messages from a list of WeChat group chats within a date range
and saves them to a JSON file for later event extraction.

Usage:
    python fetch_group_messages.py

Edit the CONFIG section below to set your group chats and date range.
"""

import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import get_chat_history, resolve_username, get_contact_names

# ============================================================
# CONFIG — edit this section
# ============================================================

GROUP_CHATS = [
    'On campus Int. Students',
        'Building F FY25',
        'UG Class of 2028',
        'DKU Film Society',
        'Building G 25-26',
        'DKU28 ONLY for Grade 1', 
        'Superdeep', 
        'DKU Music Night', 
        'UG Class of 2029', 
        'DKU MUN Club', 
        'Building H 25-26'
]

START_DATE = "2026-02-01"   # YYYY-MM-DD
END_DATE   = "2026-03-15"   # YYYY-MM-DD

MAX_MESSAGES_PER_GROUP = 2000   # upper limit per group

OUTPUT_FILE = "group_messages.json"   # saved in same folder as this script

# ============================================================

def fetch_all(groups, start, end, limit):
    results = {}
    names = get_contact_names()
    total = 0

    print(f"\nFetching messages from {start} to {end}")
    print("=" * 50)

    for group in groups:
        print(f"\n→ {group} ...", end=" ", flush=True)

        username = resolve_username(group)
        if not username:
            print(f"SKIPPED (not found)")
            results[group] = {"error": "contact not found", "messages": []}
            continue

        display = names.get(username, username)
        raw = get_chat_history(
            group,
            limit=limit,
            start_time=start,
            end_time=end
        )

        # parse the text output into individual message lines
        lines = raw.strip().splitlines()

        # strip the header line(s) — everything before the first [timestamp] line
        msg_lines = [l for l in lines if l.startswith("[20")]

        print(f"{len(msg_lines)} messages")
        total += len(msg_lines)

        results[group] = {
            "username": username,
            "display_name": display,
            "start": start,
            "end": end,
            "message_count": len(msg_lines),
            "messages": msg_lines,
        }

    print(f"\n{'=' * 50}")
    print(f"Total: {total} messages across {len(groups)} group(s)")
    return results


def main():
    data = fetch_all(GROUP_CHATS, START_DATE, END_DATE, MAX_MESSAGES_PER_GROUP)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {out_path}")
    print("Next step: run  python extract_events.py")


if __name__ == "__main__":
    main()