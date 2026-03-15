#!/usr/bin/env python3
"""
unai.py - HTTP utility module for Unai skills

Provides a simple HTTP interface with fallback support for different environments.
"""

import urllib.request
import urllib.error
import json
from typing import Optional, Dict, Any

class HTTPResponse:
    """Simple HTTP response wrapper."""
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code
    
    def json(self) -> Dict[str, Any]:
        """Parse JSON content."""
        try:
            return json.loads(self.content.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    
    def text(self) -> str:
        """Get content as text."""
        return self.content.decode('utf-8', errors='ignore')

def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Optional[HTTPResponse]:
    """
    Perform HTTP GET request with fallback support.
    
    Args:
        url: The URL to request
        headers: Optional HTTP headers
        timeout: Request timeout in seconds
    
    Returns:
        HTTPResponse object or None if request fails
    """
    try:
        req = urllib.request.Request(url)
        
        # Set headers
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        
        # Set user agent if not provided
        if not headers or 'User-Agent' not in headers:
            req.add_header('User-Agent', 'Unai/1.0')
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
            return HTTPResponse(content, response.getcode())
            
    except urllib.error.URLError as e:
        # Handle network errors, SSL errors, etc.
        return None
    except urllib.error.HTTPError as e:
        # Handle HTTP errors (4xx, 5xx)
        return HTTPResponse(b'', e.code)
    except Exception:
        # Handle any other exceptions
        return None

def post(url: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Optional[HTTPResponse]:
    """
    Perform HTTP POST request with fallback support.
    
    Args:
        url: The URL to request
        data: Optional data to send (will be JSON-encoded)
        headers: Optional HTTP headers
        timeout: Request timeout in seconds
    
    Returns:
        HTTPResponse object or None if request fails
    """
    try:
        req = urllib.request.Request(url, method='POST')
        
        # Set headers
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        
        # Set content type and data
        if data:
            json_data = json.dumps(data).encode('utf-8')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Content-Length', str(len(json_data)))
        else:
            json_data = b''
        
        # Set user agent if not provided
        if not headers or 'User-Agent' not in headers:
            req.add_header('User-Agent', 'Unai/1.0')
        
        with urllib.request.urlopen(req, data=json_data, timeout=timeout) as response:
            content = response.read()
            return HTTPResponse(content, response.getcode())
            
    except urllib.error.URLError as e:
        return None
    except urllib.error.HTTPError as e:
        return HTTPResponse(b'', e.code)
    except Exception:
        return None
