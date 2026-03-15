"""
extract_events.py

Reads group_messages.json produced by fetch_group_messages.py,
sends messages to DeepSeek API in batches, and extracts calendar events.

Output: events.json  +  events.csv

Usage:
    python extract_events.py

Requirements:
    pip install openai

API key: https://platform.deepseek.com -> API Keys (free credits on signup)
DeepSeek uses the OpenAI-compatible API format.
"""

import os, sys, json, time, csv
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    print("Missing dependency. Run:  pip install openai")
    sys.exit(1)

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE  = "group_messages.json"
OUTPUT_JSON = "events.json"
OUTPUT_CSV  = "events.csv"

# How many message lines to send per API call.
BATCH_SIZE = 150

# DeepSeek model
# deepseek-chat     = DeepSeek V3  (fast, cheap, good for structured tasks)
# deepseek-reasoner = DeepSeek R1  (slower, overkill for this task)
MODEL = "deepseek-chat"

# ============================================================

CSV_FIELDS = [
    "event_name",
    "event_date",
    "event_time",
    "category",
    "location",
    "description",
    "organizer",
    "food_provided",
    "food_details",
    "application_required",
    "application_link",
    "source_group",
]

SYSTEM_PROMPT = """You are an assistant that extracts calendar events and activities from WeChat group chat messages.

Your job is to read a batch of chat messages and identify any mentions of:
- Meetings, calls, or gatherings (online or in-person)
- Deadlines or due dates
- Scheduled activities, classes, events, or trips
- Reminders or time-sensitive announcements
- Social events, workshops, seminars, info sessions, career fairs, etc.

For each event found, return a JSON array. Each event object must have exactly these fields:

{
  "event_name": "short, descriptive event title",
  "event_date": "YYYY-MM-DD, or null if unknown",
  "event_time": "HH:MM in 24h format, or null if not mentioned",
  "category": "one of: Academic / Career / Social / Sports / Workshop / Seminar / Deadline / Meeting / Other",
  "location": "venue name, address, or Online, or null if not mentioned",
  "description": "1-2 sentence summary of the event",
  "organizer": "person or organization hosting the event, or null if not mentioned",
  "food_provided": true or false,
  "food_details": "description of food if food_provided is true, otherwise null",
  "application_required": true or false,
  "application_link": "URL if mentioned, otherwise null"
}

Rules:
- Only extract real events with a time/date component. Ignore general chatter.
- If a date is relative (e.g. "this Friday", "next Monday"), do your best to resolve it from context; if you cannot, set event_date to null and mention it in description.
- If a message is not in English, still extract the event and write ALL output fields in English.
- food_provided and application_required must be boolean true or false -- never null or a string.
- If there are no events in the batch, return an empty array: []
- Return ONLY a valid JSON array. No explanation, no markdown fences, no preamble."""


def extract_events_from_batch(client, messages, group_name):
    """Send one batch of messages to DeepSeek and return parsed events."""
    content = f"Group: {group_name}\n\nMessages:\n" + "\n".join(messages)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": content},
        ],
        max_tokens=3000,
        temperature=0.0,  # deterministic output for structured extraction
    )

    raw = response.choices[0].message.content.strip()

    # strip markdown fences if model added them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        events = json.loads(raw)
        if not isinstance(events, list):
            return []
        # normalise booleans -- model sometimes returns strings
        for e in events:
            for bool_field in ("food_provided", "application_required"):
                val = e.get(bool_field)
                if isinstance(val, str):
                    e[bool_field] = val.strip().lower() in ("true", "yes", "1")
                elif val is None:
                    e[bool_field] = False
        return events
    except json.JSONDecodeError:
        print(f"    [WARN] Could not parse response for {group_name}, skipping batch")
        return []


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def sort_key(e):
    d = e.get("event_date") or "9999-12-31"
    t = e.get("event_time") or "23:59"
    return (d, t)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, INPUT_FILE)

    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}")
        print("Run fetch_group_messages.py first.")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        group_data = json.load(f)

    # get API key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        api_key = input("Enter your DeepSeek API key: ").strip()
    if not api_key:
        print("No API key provided.")
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    all_events = []
    total_batches = 0

    print(f"\nExtracting events from {len(group_data)} group(s)")
    print("=" * 50)

    for group_name, info in group_data.items():
        if info.get("error"):
            print(f"\n  {group_name}: skipped ({info['error']})")
            continue

        messages = info.get("messages", [])
        if not messages:
            print(f"\n-  {group_name}: no messages")
            continue

        batches = list(chunk(messages, BATCH_SIZE))
        print(f"\n-> {group_name}  ({len(messages)} msgs, {len(batches)} batches)")

        group_events = []
        for i, batch in enumerate(batches):
            print(f"   batch {i+1}/{len(batches)} ...", end=" ", flush=True)
            try:
                events = extract_events_from_batch(client, batch, group_name)
                for e in events:
                    e["source_group"] = group_name
                group_events.extend(events)
                total_batches += 1
                print(f"{len(events)} event(s) found")
                if i < len(batches) - 1:
                    time.sleep(0.5)
            except Exception as ex:
                print(f"ERROR: {ex}")
                time.sleep(3)  # back off on error

        all_events.extend(group_events)
        print(f"   subtotal: {len(group_events)} event(s)")

    all_events.sort(key=sort_key)

    print(f"\n{'=' * 50}")
    print(f"Total events extracted: {len(all_events)} (from {total_batches} batches)")

    # ---- save JSON ----
    json_path = os.path.join(script_dir, OUTPUT_JSON)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON -> {json_path}")

    # ---- save CSV ----
    csv_path = os.path.join(script_dir, OUTPUT_CSV)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        # utf-8-sig so Excel opens it correctly without garbled characters
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for e in all_events:
            row = {field: e.get(field, "") for field in CSV_FIELDS}
            row["food_provided"] = "TRUE" if e.get("food_provided") else "FALSE"
            row["application_required"] = "TRUE" if e.get("application_required") else "FALSE"
            writer.writerow(row)
    print(f"Saved CSV  -> {csv_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
    
# """
# extract_events.py

# Reads group_messages.json produced by fetch_group_messages.py,
# sends messages to Gemini API in batches, and extracts calendar events.

# Output: events.json  +  events.csv

# Usage:
#     python extract_events.py

# Requirements:
#     pip install google-generativeai

# Free API key: https://aistudio.google.com -> Get API Key (no credit card needed)
# """

# import os, sys, json, time, csv
# from datetime import datetime

# try:
#     import google.generativeai as genai
# except ImportError:
#     print("Missing dependency. Run:  pip install google-generativeai")
#     sys.exit(1)

# # ============================================================
# # CONFIG
# # ============================================================

# INPUT_FILE  = "group_messages.json"
# OUTPUT_JSON = "events.json"
# OUTPUT_CSV  = "events.csv"

# # How many message lines to send per API call.
# # Gemini Flash has a large context window so 150 is fine.
# BATCH_SIZE = 150

# # Gemini model -- gemini-1.5-flash is free tier
# MODEL = "gemini-2.5-flash"

# # ============================================================

# CSV_FIELDS = [
#     "event_name",
#     "event_date",
#     "event_time",
#     "category",
#     "location",
#     "description",
#     "organizer",
#     "food_provided",
#     "food_details",
#     "application_required",
#     "application_link",
#     "source_group",
# ]

# SYSTEM_PROMPT = """You are an assistant that extracts calendar events and activities from WeChat group chat messages.

# Your job is to read a batch of chat messages and identify any mentions of:
# - Meetings, calls, or gatherings (online or in-person)
# - Deadlines or due dates
# - Scheduled activities, classes, events, or trips
# - Reminders or time-sensitive announcements
# - Social events, workshops, seminars, info sessions, career fairs, etc.

# For each event found, return a JSON array. Each event object must have exactly these fields:

# {
#   "event_name": "short, descriptive event title",
#   "event_date": "YYYY-MM-DD, or null if unknown",
#   "event_time": "HH:MM in 24h format, or null if not mentioned",
#   "category": "one of: Academic / Career / Social / Sports / Workshop / Seminar / Deadline / Meeting / Other",
#   "location": "venue name, address, or Online, or null if not mentioned",
#   "description": "1-2 sentence summary of the event",
#   "organizer": "person or organization hosting the event, or null if not mentioned",
#   "food_provided": true or false,
#   "food_details": "description of food if food_provided is true, otherwise null",
#   "application_required": true or false,
#   "application_link": "URL if mentioned, otherwise null"
# }

# Rules:
# - Only extract real events with a time/date component. Ignore general chatter.
# - If a date is relative (e.g. "this Friday", "next Monday"), do your best to resolve it from context; if you cannot, set event_date to null and mention it in description.
# - If a message is not in English, still extract the event and write ALL output fields in English.
# - food_provided and application_required must be boolean true or false -- never null or a string.
# - If there are no events in the batch, return an empty array: []
# - Return ONLY a valid JSON array. No explanation, no markdown fences, no preamble."""


# def extract_events_from_batch(model, messages, group_name):
#     """Send one batch of messages to Gemini and return parsed events."""
#     content = (
#         SYSTEM_PROMPT
#         + f"\n\nGroup: {group_name}\n\nMessages:\n"
#         + "\n".join(messages)
#     )

#     response = model.generate_content(content)
#     raw = response.text.strip()

#     # strip markdown fences if Gemini added them anyway
#     if raw.startswith("```"):
#         raw = raw.split("```")[1]
#         if raw.startswith("json"):
#             raw = raw[4:]
#     raw = raw.strip()

#     try:
#         events = json.loads(raw)
#         if not isinstance(events, list):
#             return []
#         # normalise booleans -- Gemini sometimes returns strings
#         for e in events:
#             for bool_field in ("food_provided", "application_required"):
#                 val = e.get(bool_field)
#                 if isinstance(val, str):
#                     e[bool_field] = val.strip().lower() in ("true", "yes", "1")
#                 elif val is None:
#                     e[bool_field] = False
#         return events
#     except json.JSONDecodeError:
#         print(f"    [WARN] Could not parse response for {group_name}, skipping batch")
#         return []


# def chunk(lst, size):
#     for i in range(0, len(lst), size):
#         yield lst[i:i + size]


# def sort_key(e):
#     d = e.get("event_date") or "9999-12-31"
#     t = e.get("event_time") or "23:59"
#     return (d, t)


# def main():
#     script_dir = os.path.dirname(os.path.abspath(__file__))
#     input_path = os.path.join(script_dir, INPUT_FILE)

#     if not os.path.exists(input_path):
#         print(f"Input file not found: {input_path}")
#         print("Run fetch_group_messages.py first.")
#         sys.exit(1)

#     with open(input_path, encoding="utf-8") as f:
#         group_data = json.load(f)

#     # get API key
#     api_key = os.environ.get("GEMINI_API_KEY", "")
#     if not api_key:
#         api_key = input("Enter your Gemini API key: ").strip()
#     if not api_key:
#         print("No API key provided.")
#         sys.exit(1)

#     genai.configure(api_key=api_key)
#     model = genai.GenerativeModel(MODEL)

#     all_events = []
#     total_batches = 0

#     print(f"\nExtracting events from {len(group_data)} group(s)")
#     print("=" * 50)

#     for group_name, info in group_data.items():
#         if info.get("error"):
#             print(f"\n  {group_name}: skipped ({info['error']})")
#             continue

#         messages = info.get("messages", [])
#         if not messages:
#             print(f"\n-  {group_name}: no messages")
#             continue

#         batches = list(chunk(messages, BATCH_SIZE))
#         print(f"\n-> {group_name}  ({len(messages)} msgs, {len(batches)} batches)")

#         group_events = []
#         for i, batch in enumerate(batches):
#             print(f"   batch {i+1}/{len(batches)} ...", end=" ", flush=True)
#             try:
#                 events = extract_events_from_batch(model, batch, group_name)
#                 for e in events:
#                     e["source_group"] = group_name
#                 group_events.extend(events)
#                 total_batches += 1
#                 print(f"{len(events)} event(s) found")
#                 if i < len(batches) - 1:
#                     time.sleep(1)  # stay within free tier rate limits
#             except Exception as ex:
#                 print(f"ERROR: {ex}")
#                 time.sleep(3)  # back off on error

#         all_events.extend(group_events)
#         print(f"   subtotal: {len(group_events)} event(s)")

#     all_events.sort(key=sort_key)

#     print(f"\n{'=' * 50}")
#     print(f"Total events extracted: {len(all_events)} (from {total_batches} batches)")

#     # ---- save JSON ----
#     json_path = os.path.join(script_dir, OUTPUT_JSON)
#     with open(json_path, "w", encoding="utf-8") as f:
#         json.dump(all_events, f, ensure_ascii=False, indent=2)
#     print(f"Saved JSON -> {json_path}")

#     # ---- save CSV ----
#     csv_path = os.path.join(script_dir, OUTPUT_CSV)
#     with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
#         # utf-8-sig so Excel opens it correctly without garbled characters
#         writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
#         writer.writeheader()
#         for e in all_events:
#             row = {field: e.get(field, "") for field in CSV_FIELDS}
#             # convert booleans to TRUE/FALSE strings for readability in Excel
#             row["food_provided"] = "TRUE" if e.get("food_provided") else "FALSE"
#             row["application_required"] = "TRUE" if e.get("application_required") else "FALSE"
#             writer.writerow(row)
#     print(f"Saved CSV  -> {csv_path}")
#     print("\nDone.")


# if __name__ == "__main__":
#     main()