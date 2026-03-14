"""Wikipedia summary skill"""
import re
import urllib.parse
import unai

_TRIGGERS = re.compile(
    r'(what is|what\'s|who is|tell me about)',
    re.IGNORECASE
)

def match(text):
    return bool(_TRIGGERS.search(text))

def _clean(text):
    # Extract search keyword
    patterns = [
        r'what(?:\'s| is)\s+(.+?)(?:\?|$)',
        r'who is\s+(.+?)(?:\?|$)',
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

    encoded = urllib.parse.quote(keyword)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    try:
        response = unai.get(url, headers={"User-Agent": "Unai/1.0"}, timeout=5)
        if response is None:
            return None

        data = response.json()

        title = data.get("title", keyword)
        extract = data.get("extract", "")
        if not extract:
            return None

        # First 2 sentences only
        sentences = re.split(r'\.', extract)
        summary = ".".join(sentences[:2]) + ("." if len(sentences) > 1 else "")
        return f"【{title}】\n{summary}"

    except Exception:
        return None
