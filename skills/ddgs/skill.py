"""DDGS (DuckDuckGo Search) summary skill"""
import re
from ddgs import DDGS

_TRIGGERS = re.compile(
    r'(search|find|look up|ddgs|what is|what\'s|who is|who\'s|tell me about)',
    re.IGNORECASE
)

def match(text):
    return bool(_TRIGGERS.search(text))

def _clean(text):
    # Extract search keyword
    patterns = [
        r'search\s+(?:for\s+)?(.+?)(?:\?|$)',
        r'find\s+(.+?)(?:\?|$)',
        r'look up\s+(.+?)(?:\?|$)',
        r'ddgs\s+(.+?)(?:\?|$)',
        r'what is\s+(.+?)(?:\?|$)',
        r'what\'s\s+(.+?)(?:\?|$)',
        r'who is\s+(.+?)(?:\?|$)',
        r'who\'s\s+(.+?)(?:\?|$)',
        r'tell me about\s+(.+?)(?:\?|$)',
    ]
    for p in patterns:
        m = re.search(p, text.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return text.strip()

def respond(text):
    keyword = _clean(text)
    if not keyword:
        return None

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(keyword, max_results=3))
            
        if not results:
            return "No search results found."
        
        # Extract and summarize the first result
        first_result = results[0]
        title = first_result.get('title', '')
        body = first_result.get('body', '')
        
        if not body:
            return "Could not retrieve summary."
        
        # Limit summary to first 2-3 sentences
        sentences = re.split(r'[.!?]', body)
        summary = '.'.join(sentences[:3]).strip()
        if summary and not summary.endswith('.'):
            summary += '.'
        
        return f"【{title}】\n{summary}"
        
    except Exception:
        return "An error occurred during search."
