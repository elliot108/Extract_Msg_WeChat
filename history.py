# history.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the already-built logic from mcp_server.py
from mcp_server import (
    get_recent_sessions,
    get_chat_history,
    search_messages,
    get_contacts,
)

def menu():
    print("\n=== WeChat History Viewer ===")
    print("1. Recent sessions")
    print("2. Chat history")
    print("3. Search messages")
    print("4. Find a contact")
    print("q. Quit")
    return input("\nChoice: ").strip()

while True:
    choice = menu()

    if choice == 'q':
        break

    elif choice == '1':
        n = input("How many sessions? [20]: ").strip()
        print(get_recent_sessions(int(n) if n else 20))

    elif choice == '2':
        name = input("Contact name (or wxid): ").strip()
        n = input("How many messages? [50]: ").strip()
        start = input("Start date (YYYY-MM-DD or blank): ").strip()
        end = input("End date (YYYY-MM-DD or blank): ").strip()
        print(get_chat_history(name, int(n) if n else 50, start_time=start, end_time=end))

    elif choice == '3':
        keyword = input("Search keyword: ").strip()
        name = input("Limit to contact (or blank for all): ").strip()
        start = input("Start date (YYYY-MM-DD or blank): ").strip()
        end = input("End date (YYYY-MM-DD or blank): ").strip()
        print(search_messages(keyword, chat_name=name or None, start_time=start, end_time=end))

    elif choice == '4':
        query = input("Name to search: ").strip()
        print(get_contacts(query))