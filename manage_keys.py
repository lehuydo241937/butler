
import argparse
import sys
from secrets_manager.redis_secrets import RedisSecretsManager
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Manage API keys in Redis.")
    parser.add_argument("action", choices=["set", "get", "delete", "list"], help="Action to perform")
    parser.add_argument("service", help="Service name (e.g., gemini)", nargs="?")
    parser.add_argument("key", help="API Key value (for set action)", nargs="?")

    args = parser.parse_args()
    secrets = RedisSecretsManager()

    # Simple ping check using the underlying client
    try:
        secrets.r.ping()
    except Exception:
        print("Error: Cannot connect to Redis.")
        sys.exit(1)

    if args.action == "set":
        if not args.service or not args.key:
            print("Usage: manage_keys.py set <service> <key>")
            sys.exit(1)
        secrets.set_secret(args.service, args.key)
        print(f"Secret for '{args.service}' set successfully.")

    elif args.action == "get":
        if not args.service:
            print("Usage: manage_keys.py get <service>")
            sys.exit(1)
        key = secrets.get_secret(args.service)
        if key:
            print(f"Secret for '{args.service}': {key}")
        else:
            print(f"No secret found for '{args.service}'.")

    elif args.action == "delete":
        if not args.service:
            print("Usage: manage_keys.py delete <service>")
            sys.exit(1)
        secrets.delete_secret(args.service)
        print(f"Secret for '{args.service}' deleted.")
    
    elif args.action == "list":
         keys = secrets.list_secrets()
         if keys:
             print("Stored secrets:")
             for k in keys:
                 print(f" - {k}")
         else:
             print("No secrets stored.")

if __name__ == "__main__":
    main()
