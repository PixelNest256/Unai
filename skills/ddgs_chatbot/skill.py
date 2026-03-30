"""DDGS Chatbot skill - Extracts specific answer sentences from DuckDuckGo search results"""
import re
from ddgs import DDGS

def match(text: str) -> bool:
    """Return True if this Skill should handle the input."""
    return True

def _clean(text):
    """Extract search keyword from user input"""
    patterns = [
        r'answer\s+(?:for\s+)?(.+?)(?:\?|$)',
        r'find answer\s+(?:for\s+)?(.+?)(?:\?|$)',
        r'search answer\s+(?:for\s+)?(.+?)(?:\?|$)',
        r'ddgs chatbot\s+(.+?)(?:\?|$)',
        r'what is answer\s+(?:for\s+)?(.+?)(?:\?|$)',
        r'tell me answer\s+(?:for\s+)?(.+?)(?:\?|$)',
    ]
    for p in patterns:
        m = re.search(p, text.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return text.strip()

def split_sentences(text):
    """Split text into sentences"""
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return re.split(r'(?<=[.!?])\s', text)

def is_valid_sentence(sentence, query, valves):
    """Check if sentence is valid based on valve settings"""
    s = sentence.strip()
    
    # Load valve settings with proper type conversion
    exclude_questions = str(valves.get("exclude_questions", "true")).lower() == "true"
    exclude_query_match = str(valves.get("exclude_query_match", "true")).lower() == "true"
    try:
        min_sentence_length = int(valves.get("min_sentence_length", 40))
    except (ValueError, TypeError):
        min_sentence_length = 40
    
    # Condition 1: Exclude questions (if enabled)
    if exclude_questions and s.endswith("?"):
        return False
    
    # Condition 2: Exclude query matches (if enabled)
    if exclude_query_match:
        q = query.lower().strip(" ?")
        if q in s.lower():
            return False
    
    # Condition 3: Minimum sentence length (if enabled)
    if min_sentence_length > 0 and len(s) < min_sentence_length:
        return False
    
    return True

def extract_answer_sentence(text, query, valves):
    """Extract the first valid answer sentence from text"""
    sentences = split_sentences(text)
    
    for sentence in sentences:
        if is_valid_sentence(sentence, query, valves):
            return sentence
    
    return None

def respond(text: str) -> str:
    """Return the response string, or None to skip this Skill."""
    keyword = _clean(text)
    if not keyword:
        return None
    
    # Load valve settings with proper type conversion
    valves = load_valves()
    try:
        max_results = int(valves.get("max_results", 8))
    except (ValueError, TypeError):
        max_results = 8
    
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(keyword, max_results=max_results):
                results.append(r)
        
        if not results:
            return "No search results found."
        
        for r in results:
            body = r.get("body", "")
            if not body:
                continue
            
            # Normalize text spacing
            # 1. Add space at camelCase boundaries (aB -> a B, 5B -> 5 B)
            body = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', body)
            # 2. Add space between letter and number (a5 -> a 5)
            body = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', body)
            # 3. Add space after punctuation
            body = re.sub(r'([,!?])([^ \n])', r'\1 \2', body)
            body = re.sub(r'(\.)([^ \n\d])', r'\1 \2', body)
            # 4. Normalize whitespace
            body = re.sub(r"\s+", " ", body).strip()
            
            sentence = extract_answer_sentence(body, keyword, valves)
            if sentence:
                return sentence
        
        return "No relevant answer found."
        
    except Exception as e:
        return f"An error occurred during search: {str(e)}"
