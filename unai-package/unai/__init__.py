import os
import re
import requests
from typing import List, Optional
import warnings

def _read_request_urls() -> List[str]:
    """
    Read request_urls.txt from the same directory as the calling script.
    Returns a list of URL patterns (regex or exact URLs), one per line.
    """
    # Get the directory of the calling script by walking up the stack
    import inspect
    frame = inspect.currentframe()
    caller_dirs = []
    
    # Walk up the stack to collect all potential caller directories
    while frame:
        frame = frame.f_back
        if frame and not frame.f_globals.get('__name__', '').startswith('unai'):
            caller_file = frame.f_globals.get('__file__')
            if caller_file:
                caller_dir = os.path.dirname(os.path.abspath(caller_file))
                caller_dirs.append(caller_dir)
    
    # Check each directory for request_urls.txt, starting from the most recent caller
    # (the one closest to the actual request)
    for caller_dir in caller_dirs:
        urls_file = os.path.join(caller_dir, 'request_urls.txt')
        if os.path.exists(urls_file):
            try:
                with open(urls_file, 'r', encoding='utf-8-sig') as f:
                    patterns = [line.strip() for line in f if line.strip()]
                return patterns
            except Exception as e:
                warnings.warn(f"Error reading request_urls.txt from {caller_dir}: {e}")
                continue
    
    # Fallback to current working directory if we can't determine the caller
    caller_dir = os.getcwd()
    urls_file = os.path.join(caller_dir, 'request_urls.txt')
    
    if os.path.exists(urls_file):
        try:
            with open(urls_file, 'r', encoding='utf-8-sig') as f:
                patterns = [line.strip() for line in f if line.strip()]
            return patterns
        except Exception as e:
            warnings.warn(f"Error reading request_urls.txt: {e}")
    
    warnings.warn(f"request_urls.txt not found in any caller directory or {caller_dir}")
    return []

def _is_url_allowed(url: str, patterns: List[str]) -> bool:
    """
    Check if URL matches any of the allowed patterns.
    Patterns can be exact URLs or regex patterns.
    """
    for pattern in patterns:
        try:
            # Try to match as regex first
            if re.fullmatch(pattern, url):
                return True
        except re.error:
            # If it's not a valid regex, treat as exact match
            if url == pattern:
                return True
    return False

def request(url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
    """
    Send a request only if the URL matches patterns in request_urls.txt.
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        **kwargs: Additional arguments passed to requests.request
    
    Returns:
        requests.Response object if URL is allowed, None otherwise
    """
    patterns = _read_request_urls()
    
    if not _is_url_allowed(url, patterns):
        warnings.warn(f"URL {url} not found in request_urls.txt patterns. Request blocked.")
        return None
    
    try:
        response = requests.request(method, url, **kwargs)
        return response
    except Exception as e:
        warnings.warn(f"Request failed: {e}")
        return None

def get(url: str, **kwargs) -> Optional[requests.Response]:
    """Send GET request if URL is allowed."""
    return request(url, 'GET', **kwargs)

def post(url: str, **kwargs) -> Optional[requests.Response]:
    """Send POST request if URL is allowed."""
    return request(url, 'POST', **kwargs)

def put(url: str, **kwargs) -> Optional[requests.Response]:
    """Send PUT request if URL is allowed."""
    return request(url, 'PUT', **kwargs)

def delete(url: str, **kwargs) -> Optional[requests.Response]:
    """Send DELETE request if URL is allowed."""
    return request(url, 'DELETE', **kwargs)
