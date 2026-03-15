"""Random joke skill"""
import re
import random

JOKES = [
    "Why do programmers wear glasses?\n→ Because they can't C#.",
    "Why don't scientists trust door knobs?\n→ Because they're always twisting things.",
    "A mathematician walks into a bank to rob it.\n\"Nobody move, this is an optimization problem!\"",
    "Why do skeletons have so few friends?\n→ Because they're always telling bone-chilling stories.",
    "A programmer's wife said, \"Go to the store and get a carton of milk. If they have eggs, get six.\"\nThe programmer came back with 6 cartons of milk.",
    "Why doesn't the sun go to school?\n→ Because it already has a million degrees.",
    "I asked a quantum computer, \"How are you doing?\"\n\"Good and bad at the same time.\"",
]

_TRIGGERS = re.compile(r'joke|laugh|funny|hilarious|joking', re.IGNORECASE)

def match(text):
    return bool(_TRIGGERS.search(text))

def respond(text):
    return random.choice(JOKES)
