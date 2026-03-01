import socket
import urllib.request
import sys

def check_connectivity(host, port, timeout=5):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        print(f"SUCCESS: Connected to {host}:{port}")
        return True
    except Exception as e:
        print(f"FAILURE: Could not connect to {host}:{port}: {e}")
        return False

def check_https(url):
    try:
        response = urllib.request.urlopen(url, timeout=10)
        print(f"SUCCESS: Accessed {url} (Status: {response.getcode()})")
        return True
    except Exception as e:
        print(f"FAILURE: Could not access {url}: {e}")
        return False

if __name__ == "__main__":
    print("--- Connectivity Test ---")
    check_connectivity("www.google.com", 443)
    check_connectivity("gmail.googleapis.com", 443)
    check_connectivity("accounts.google.com", 443)
    check_connectivity("oauth2.googleapis.com", 443)
    
    print("\n--- HTTPS Test ---")
    check_https("https://www.google.com")
    check_https("https://gmail.googleapis.com")
