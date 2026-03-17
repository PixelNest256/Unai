"""Greeting & small talk skill using rule-based matching + Levenshtein distance"""

RULES = [
    (["hello", "hi", "hey", "yoo"],
     ["Hello! Is there anything I can help you with?", "Hey! How are you?", "Hello!"]),
    (["good morning"],
     ["Good morning! Have a great day today.", "Good morning!"]),
    (["good evening"],
     ["Good evening! How was your day?"]),
    (["thank", "thanks"],
     ["You're welcome!", "Glad to help!"]),
    (["how are you", "how do you do"],
     ["I'm doing well! How about you?"]),
    (["bye", "goodbye"],
     ["See you later! Have a great day!", "Goodbye! Come back anytime."]),
    (["what's up", "whats up"],
     ["Not much, just here to help!"]),
    (["who are you", "what are you"],
     ["I'm Unai, your Non-AI assistant!"]),
    (["what can you do", "what are your capabilities"],
     ["I can help you with basic questions, greetings, and small talk. See more by typing /help"]),
]

import random

def _levenshtein(a, b):
    a, b = a.lower(), b.lower()
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        ndp = [i + 1]
        for j, cb in enumerate(b):
            ndp.append(min(dp[j] + (0 if ca == cb else 1),
                           dp[j+1] + 1, ndp[j] + 1))
        dp = ndp
    return dp[-1]

def match(text):
    text_l = text.lower()
    for keywords, _ in RULES:
        for kw in keywords:
            dist = _levenshtein(text_l, kw)
            threshold = max(1, len(kw) // 4)
            if dist <= threshold or kw in text_l:
                return True
    return False

def respond(text):
    text_l = text.lower()
    for keywords, responses in RULES:
        for kw in keywords:
            dist = _levenshtein(text_l, kw)
            threshold = max(1, len(kw) // 4)
            if dist <= threshold or kw in text_l:
                return random.choice(responses)
    return "Hello! Is there anything I can help you with?"
