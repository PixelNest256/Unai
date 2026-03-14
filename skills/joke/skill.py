"""Random joke skill"""
import re
import random

JOKES = [
    "なぜプログラマーはメガネをかけるのか？\n→ C# が見えないから。",
    "なぜ科学者はドアノブを信頼しないのか？\n→ いつも何かをひねっているから。",
    "数学者が銀行に強盗に入った。\n「全員動くな、これは最適化問題だ！」",
    "なぜスケルトンは友達が少ないのか？\n→ 骨が折れる話ばかりするから。",
    "プログラマーの妻が言った。「買い物に行って牛乳を1本買ってきて。卵があったら6個ね。」\nプログラマーは牛乳を6本買って帰った。",
    "なぜ太陽は学校に行かないのか？\n→ すでに100万度の熱を持っているから。",
    "量子コンピューターに聞いた。「調子はどう？」\n「良くもあり、悪くもある。」",
]

_TRIGGERS = re.compile(r'joke|ジョーク|笑|おもしろ|面白|ふざけ', re.IGNORECASE)

def match(text):
    return bool(_TRIGGERS.search(text))

def respond(text):
    return random.choice(JOKES)
