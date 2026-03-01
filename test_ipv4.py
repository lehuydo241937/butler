import httplib2
import socket

def test_httplib2_ipv4_only():
    print("Testing httplib2 with forced IPv4...")
    
    # Monkey-patch socket to force IPv4 for this demonstration
    original_getaddrinfo = socket.getaddrinfo
    def forced_getaddrinfo(*args, **kwargs):
        # Filter for AF_INET (IPv4)
        return original_getaddrinfo(args[0], args[1], socket.AF_INET, *args[3:])
    
    socket.getaddrinfo = forced_getaddrinfo
    
    try:
        h = httplib2.Http(timeout=10)
        # Choose an endpoint that httplib2 previously failed on
        url = "https://gmail.googleapis.com/discovery/v1/apis/gmail/v1/rest"
        print(f"Requesting {url}...")
        resp, content = h.request(url)
        print(f"SUCCESS: Status {resp.status}")
    except Exception as e:
        print(f"FAILURE: {e}")
    finally:
        socket.getaddrinfo = original_getaddrinfo

if __name__ == "__main__":
    test_httplib2_ipv4_only()
