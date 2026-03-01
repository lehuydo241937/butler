import socket
import logging

logger = logging.getLogger(__name__)

def force_ipv4():
    """
    Monkey-patch socket.getaddrinfo to prioritize or force IPv4 (AF_INET).
    This resolves timeouts in environments with broken IPv6 connectivity
    where httplib2 (used by Google API clients) stalls on unreachable IPs.
    """
    original_getaddrinfo = socket.getaddrinfo

    def filtered_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # If family is unspecified (0), force it to AF_INET
        if family == 0:
            family = socket.AF_INET
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = filtered_getaddrinfo
    logger.info("Global socket monkey-patch applied: Forcing IPv4 preference.")
