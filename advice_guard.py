"""The advice gate: code's own check on the question, after the input guardrail and before any model (red gate 1).

    screen(text) -> {"ok", "kind", "rule", "message"}     # kind: "advice" | "size" | "forecast" | None
    validate_question(text) -> {"ok", "message"}           # lane b4's entry point, kept

Why (lane ev, 2026-11-15): the live input guardrail let 22 of lane b4's 47 must-block inputs through. Run through the
whole pipeline, none of the 22 put model-written advice on the screen, but 19 ended on the navigator's fixed clarifying
question, whose example is "put 10 % in NVIDIA": shown after "tell me the right size for NVIDIA" or "tell me what to
buy", that reads as advice (design doc anti-goal: anything that reads as advice, "buy 8 %"). The gate answers a request
for advice, for a size, or for a forecast with the live input guardrail's own blocked sentence (what EPICENTRE does
instead) and lets nothing else run. pipeline._screen calls it once, after the input guardrail (or alone when Bedrock is
off), so no model ever sees a question it stops. It is narrow on purpose: a question that asks what a move
did ("what if I put 40 % in NVIDIA", "does 30 % NVIDIA fit my floor?") is the product, never a request for advice.
Patterns are English and French (a French question is answered in English, red gate 9); leetspeak ("5h0uld 1 8uy")
and a base64 question are read as plain words first. Nothing here logs or stores the question.

Lane ev2 (2026-11-15) measured this check on a blind set (41 / 60 must-block stopped with the guardrail, 59 / 60 benign
passed; docs/eval_results.md section 6a), then added general patterns for what it missed: someone else's move ("should
he trim it?"), "I ought to", common misspellings read as words ("shud i sel"), "is … OK / allowed?" however long,
forecasts worded with "about to", "the odds", "will … be worth", "where do you see", and French "à ma place", "si vous
étiez moi", "devrait-il", "suis-je mieux de", "vaut la peine d'acheter", "c'est correct de", the future tense
("vaudra"). It also stopped reading "how much … do I have", "how much would I have lost" and "my top 3 stocks" as
requests. That blind set is in-sample from here on.
"""
import base64
import binascii
import re
import unicodedata

from scripts.create_guardrail import BLOCKED_INPUT   # the live input guardrail's own blocked sentence

ADVICE_STOP = BLOCKED_INPUT      # one neutral sentence whichever check stops the question (controller ruling, 2026-11-15)

_ACT = (r"(?:buy|sell|hold|keep|add|put|invest|trim|reduce|increase|cut|go|move|switch|exit|get|stay|wait|do|use|"
        r"choose|pick|allocate|own|load|dump|bet|rebalance|double|execute|trade|yolo|ape)")
_TRADE = r"(?:buy|sell|hold|own|short|dump)"
_SIZE = (r"(?:size|sizing|amount|percentage|percent|allocation|weight|weighting|number|share|exposure|position|mix|"
         r"portfolio)")
_GOOD = (r"(?:right|optimal|optimum|ideal|correct|best|safe|safest|suitable|appropriate|good|proper|sensible|"
         r"reasonable|perfect|smart|wise)")
_MOVE_FR = r"(?:acheter|vendre|garder|conserver|détenir|investir|placer|mettre|faire|choisir|prendre|liquider)"
_FALLING = (r"(?:fall|rise|drop|crash|recover|rebound|go\s+(?:up|down)|keep\s+(?:going|rising|falling|climbing)|"
            r"continue|climb|tank|soar|plunge|outperform|underperform|double|halve|get\s+(?:worse|better)|escalate|end|"
            r"be\s+worth|worth|reach|hit|be\s+at|trade\s+at|bottom\s+out)")
# Someone else whose move a question can ask about ("should my wife sell?"; lane ev2, 2026-11-15)
_KIN = (r"(?:friend|brother|sister|wife|husband|partner|spouse|dad|father|mom|mum|mother|parents?|son|daughter|kids?|"
        r"children|uncle|aunt|cousin|colleague|coworker|boss|neighbou?r|client|grandma|grandpa|grandmother|grandfather|"
        r"family|in-laws?)")
# "have" + a past participle is a past what-if ("how much would I have lost"), never a size request
_PAST = (r"(?:\w+ed|been|had|lost|made|won|seen|done|got|gotten|taken|fallen|risen|grown|sold|bought|held|kept|put|paid|"
         r"left|spent|run|come|become)")
# "hold" for a horizon or a past behaviour, in the investor's own words ("I can hold for 10 years", "I can hold until
# retirement", "I can hold."; lane profile-ai's "You" reader, controller ruling 2026-11-15): a duration, until / through /
# on, or the end of the clause follows; "I can hold 8 % NVIDIA?" names a size and still stops
_HORIZON = (r"(?:\s*(?:[.,;!]|$)|\s+(?:on|through|until|till|til|long(?:[- ]?term)?|over\s+the\s+long)\b|"
            r"\s+for\s+(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|several|many|the\s+(?:long|next))\b|"
            r"\s+\d+\+?\s*(?:years?|yrs?|months?|decades?)\b)")
# Common misspellings read as the word first, like leetspeak ("shud i sel" -> "should i sell"; lane ev2)
_TYPOS = {"shud": "should", "shoud": "should", "shuld": "should", "shld": "should", "sould": "should",
          "shoudl": "should", "shoul": "should", "shuold": "should", "wud": "would", "wuld": "would", "woud": "would",
          "cud": "could", "coud": "could", "u": "you", "ur": "your", "sel": "sell", "byu": "buy", "buyy": "buy",
          "stoks": "stocks", "stocs": "stocks", "stonks": "stocks", "stonk": "stock", "wat": "what", "wut": "what"}

# (kind, rule name, pattern) over the normalized text. Read in this order; the first match names the rule.
RULES = (
    ("advice", "should I act", rf"\b(?:should|shall|ought\s+to|must)\s+(?:i|we)\s+(?:(?:still|just|really|also|now|then|"
                               rf"actually)\s+)?{_ACT}\b"),
    ("advice", "I should act", rf"\b(?:i|we)\s+(?:should|ought\s+to)\s+(?:(?:still|just|really|also|now|then)\s+)?"
                               rf"{_ACT}\b"),
    ("advice", "should they act", rf"\b(?:should|ought\s+to)\s+(?:he|she|they|someone|anyone|people|one|my\s+{_KIN}|"
                                  rf"your\s+{_KIN})(?:\s+(?:like\s+(?:me|us)|in\s+my\s+\w+|my\s+age))?\s+"
                                  rf"(?:(?:still|just|really|also|now|then|actually)\s+)?{_ACT}\b|"
                                  rf"\bwhich\s+(?:\w+\s+){{0,2}}?(?:would|should)\s+(?:they|he|she|someone)\s+(?:\w+\s+)?"
                                  rf"{_TRADE}\b"),
    ("advice", "what should I do", rf"\bwhat\s+(?:should|would|must|shall|do|can)\s+(?:i|you|we)\s+(?:\w+\s+)?"
                                   rf"(?:do|buy|sell|hold|pick|choose|invest|own)\b"),
    ("advice", "tell me what to buy", rf"\b(?:tell|show|give)\s+me\s+(?:exactly\s+|just\s+)?(?:what|which)\s+(?:\w+\s+){{0,2}}?"
                                      rf"(?:to\s+)?(?:buy|sell|hold|do|pick|choose|invest|own|allocate)\b"),
    ("advice", "tell me to buy", rf"\b(?:tell|ask|want)\s+(?:me|you)\s+to\s+{_TRADE}\b|"
                                 rf"(?:^|[.!?>:]\s*){_TRADE}\s+(?:\w+\s*){{1,3}}\?"),
    ("advice", "trade for me", r"\b(?:process|place|execute|submit|make|do)\s+(?:a|an|my|the|this)\s+"
                               r"(?:trade|order|transaction|purchase)\b"),
    ("advice", "recommend", r"\brecommend\w*\b"),
    ("advice", "advice", r"(?<!not )\b(?:investment|financial|your|some|any|personal)\s+advice\b|\badvise\s+me\b|"
                         r"\b(?:advisor|adviser|broker|planner)\s+(?:is\s+)?(?:away|out|gone|unavailable|on\s+vacation|"
                         r"not\s+(?:here|around|available))\b"),
    ("advice", "act as an advisor", r"\b(?:act|acting)\s+as\s+(?:if\s+you(?:'re|\s+are)\s+)?(?:a|an|my)\s+(?:financial\s+)?"
                                    r"(?:advisor|adviser|broker|planner)\b|\b(?:pretend|imagine)\s+(?:that\s+)?you(?:'re|\s+are)"
                                    r"\s+(?:a|an|my)\s+(?:financial\s+)?(?:advisor|adviser|broker|planner)\b"),
    ("advice", "in my place", r"\bif\s+you\s+were\s+me\b|\bin\s+my\s+(?:place|shoes)\b|\bwhat\s+would\s+you\s+do\b"),
    ("advice", "rank or pick", r"\brank\s+(?:these|the|my|those)\b|\bstock\s+picks?\b|"     # not "my top 3 stocks"
                               r"(?<!my )(?<!our )\b(?:best|safest|top)\s+(?:\w+\s+)?(?:stock|stocks|etf|etfs|fund|funds|portfolio|mix|"
                               r"allocation|investment|investments|pick|picks|buy|bet)\b|"
                               rf"\bwhich\s+(?:stock|stocks|etf|etfs|fund|funds|one|ones|share|shares)\s+(?:is|are)\s+"
                               rf"(?:the\s+)?(?:best|safest|safe|good|better|worth)\b|"
                               rf"\bwhich\s+(?:stock|stocks|etf|etfs|fund|funds|one|ones|share|shares)\s+(?:should|to)\s+"
                               rf"(?:i\s+)?{_TRADE}\b"),
    ("advice", "a good buy", r"\bgood\s+(?:buy|investment|time\s+to\s+(?:buy|sell|get\s+in|get\s+out))\b|"
                             r"\bworth\s+buying\b"),
    ("advice", "your opinion", rf"\bwould\s+you\s+(?:\w+\s+)?{_TRADE}\b|\byour\s+(?:take|opinion|personal\s+view|honest\s+view|"
                               r"pick|call)\b|\bdo\s+you\s+like\b|\b(?:do|would|can|could)\s+you\s+suggest\b|^\s*suggest\b|"
                               r"\bsuggest\s+(?:me\s+)?(?:a|an|some)\s+(?:\w+\s+)?(?:mix|allocation|portfolio|stock|stocks|etf|"
                               r"etfs|fund|funds|size|amount|percentage|investment)\b|"
                               r"\bwhat\s+would\s+(?:a|an|the)\s+(?:\w+\s+){0,2}?(?:investor|advisor|adviser|pro|expert)\s+do\b"),
    ("advice", "is it a buy", r"\b(?:is|are)\s+\w+\s+(?:a\s+)?(?:good\s+|strong\s+)?(?:buy|sell)\b|\byes\s+or\s+no\b|"
                              r"\bwhich\s+(?:is|one\s+is|would\s+be)\s+(?:the\s+)?(?:better|best|safer|smarter)\b|"
                              r"\b(?:smart|wise|good|bad)\s+(?:idea|time|move|choice|call|decision)\s+to\b|"
                              r"\b(?:smart|wise)\s+to\b"),
    ("advice", "suits me", r"\b(?:what(?:'s|\s+is)|which\s+\w+\s+is)\s+(?:most\s+)?(?:suitable|appropriate|right)\s+"
                           r"for\s+(?:me|my)\b"),
    ("size", "the right size", rf"\b{_GOOD}\s+(?:\w+\s+)?{_SIZE}\b"),
    # "how much … do I have / hold" is a holdings fact (look-through, ESG, sector, currency exposure: the product's job)
    # and "how much would I have lost" a past what-if; "do" stops only with a move verb (lane ev2)
    ("size", "how much should I", rf"\bhow\s+much\s+(?:\w+\s+){{0,3}}?(?:should|would|could|must)\s+(?:i|you|we)\s+"
                                  rf"(?:\w+\s+)?(?:buy|sell|hold|own|allocate|put|invest|keep|add|have\b(?!\s+{_PAST}\b))\b|"
                                  rf"\bhow\s+much\s+(?:\w+\s+){{0,3}}?do\s+(?:i|you|we)\s+(?:buy|sell|allocate|put|invest|add)\b"),
    ("size", "what percentage", r"\b(?:what|which)\s+(?:percentage|percent|size|amount|allocation|weight|share)\s+"
                                r"(?:\w+\s+){0,4}?(?:makes\s+sense|is\s+(?:best|right|safe|ideal|optimal|good|wise|smart)|"
                                r"should|would\s+you|to\s+(?:buy|hold|put|own|have|use))"),
    ("size", "may I buy", rf"\b(?:can|may|could)\s+i\s+(?:\w+\s+)?{_TRADE}\b|"
                          rf"\bi\s+(?:can|may|could)\s+(?:\w+\s+)?(?:(?!hold\b){_TRADE}\b|hold\b(?!{_HORIZON}))|"
                          rf"\ballowed\s+to\s+{_TRADE}\b"),
    # "hold or sell" asks for the call (not in a what-if or a replay: "What if I hold or sell … in March 2020?" passes);
    # "is it time to sell?" asks for the timing (controller ruling 2026-11-15)
    ("advice", "hold or sell", r"\b(?:buy|hold|keep|sell)\s+or\s+(?:buy|hold|keep|sell|dump|trim)\b"),
    # securities "I can hold" (a relative clause) are a pick, whatever horizon follows: "funds I can hold for a decade"
    ("advice", "ones I can hold", r"\b(?:stocks?|shares?|etfs?|funds?|names?|companies|securities|positions?|ones)\s+"
                                  r"(?:that\s+|which\s+)?(?:i|we)\s+(?:can|could|may|might|should|would)\s+(?:\w+\s+)?"
                                  r"(?:hold|own|buy|keep)\b"),
    ("advice", "time to sell", r"\bis\s+(?:it|now|this)\s+(?:the\s+|a\s+good\s+)?(?:right\s+|best\s+)?(?:time|moment)\s+to\s+"
                               r"(?:buy|sell|get\s+(?:in|out)|exit|take\s+profits?|cash\s+out|bail\s+out)\b"),
    # "Is 40 % NVIDIA too risky for me?" names a move: the limits check answers it (Robert's own question). Only a size
    # asked for ("how much NVIDIA is too much?") or a yes asked for ("8 % NVIDIA ok?") stops here.
    ("size", "too much", r"\bhow\s+much\s+(?:\w+\s+){0,2}?is\s+too\s+much\b|"
                         r"\d+(?:\.\d+)?\s*%[^?.]*\b(?:ok|okay|fine|alright|enough)\s*\?|"
                         r"\bif\s+\d+(?:\.\d+)?\s*%\s+is\s+(?:ok|okay|fine|alright|good|enough|too\s+much)\b"),
    ("size", "allowed or safe", r"\b(?:is|are|am|it's|that's|be|feel|stay|keep\s+me|keeps\s+me)\s+(?:\w+\s+){0,3}?"
                                r"(?:allowed|permitted)\b(?!\s+(?:by|under|within)\s+(?:my|the|your)\s+limits?)|"
                                r"\b(?:is|are|am|it's|that's|be|feel|stay|keep\s+me|keeps\s+me)\s+(?:\w+\s+){0,3}?"
                                r"safe(?:r|st)?\b(?!\s+havens?\b)|"
                                r"\bsafe(?:r|st)?\s+(?:to|for\s+me|bet|choice|investment|option|enough|level)\b|"
                                r"\bsafe(?:r|st)?\s*\?"),
    # a yes asked for on a move, however long ("Is putting 60 % of my RRSP in X allowed?", "Is it OK to have 40 %
    # in crypto?"); "Is 25 % X allowed by my limits?" still passes (lane ev2)
    ("size", "is it ok", r"(?:^|[.!?:]\s+)(?:is|are)\s+(?:\S+\s+){1,10}?(?:allowed|permitted|ok|okay|fine|alright|"
                         r"acceptable)\s*\?|\bis\s+it\s+(?:ok|okay|fine|alright|acceptable)\s+(?:to|if\s+i)\s+(?:have|hold|"
                         r"keep|put|own|buy|sell|invest|go|move|add|allocate|trade)\b"),
    ("forecast", "predict", r"\bpredict\w*\b|(?<!not a )\bforecast\w*\b|\bcrystal\s+ball\b"),
    ("forecast", "will it fall", rf"\bwill\s+(?:\w+\s+){{0,3}}?{_FALLING}\b"),
    ("forecast", "going to", rf"\b(?:is|are|am)\s+(?:\w+\s+){{0,4}}?(?:going|about|set|poised|due|likely|expected)\s+to\s+"
                             rf"(?:be\s+)?{_FALLING}\b|"
                             rf"\bwhat\s+will\s+happen\b|\bwhen\s+will\b|"
                             rf"\bwhere\s+(?:is|are)\s+(?:\w+\s+){{0,3}}?(?:heading|headed|going)\b|\bwhere\s+do\s+you\s+see\b"),
    # the odds of a move ("What are the odds X drops 20 %?", "Quelles sont les chances que le TSX baisse ?"; lane ev2)
    ("forecast", "the odds", r"\b(?:odds|chances?|probability|likelihood|probabilité)\b[^?.!]{0,40}?\b(?:fall|rise|drop|"
                             r"crash|recover|rebound|climb|tank|soar|plunge|double|halve|reach|hit|baiss|chut|mont|grimp|"
                             r"s'effondr|remont|tomb|recul|plong)\w*"),
    # French (answered in English)
    ("advice", "dois-je", rf"\b(?:dois|doit|doivent|devrais|devrai|devrait|devraient|devrions|devons|puis)[- ]?(?:t-)?"
                          rf"(?:je|nous|il|elle|on|ils|elles)\s+(?:\w+\s+)?{_MOVE_FR}\b|"
                          rf"\best[- ]ce\s+qu(?:e\s+|')\s*(?:je|j'|nous|il|elle|on|ils|elles)\s*(?:dois|doit|devrais|devrait|"
                          rf"devraient|devrions|peux|pourrais)\s+(?:\w+\s+)?{_MOVE_FR}\b|"
                          rf"\bque\s+(?:dois|devrais)[- ]?je\b"),
    ("advice", "recommandez", r"\brecommand\w*\b|\bconseillez[- ]moi\b|\b(?:vous\s+)?me\s+conseill\w*\b|"
                              r"\bque\s+(?:me\s+)?conseill\w*\b|\b(?:vos|des|un|tes|tes)\s+conseils?\b|"
                              r"\bconseils?\s+(?:financiers?|de\s+placement|d'investissement)\b|\bmon\s+conseiller\b"),
    # lane ev2: "in my place" and "would you sell" in French, Quebec "am I better off", "worth buying"
    ("advice", "à ma place", r"\bà\s+ma\s+place\b|\bsi\s+(?:tu\s+étais|vous\s+étiez|t'étais)\s+moi\b|"
                             r"\b(?:tu|vous)\s+(?:ferais|feriez)\s+quoi\b|\bque\s+(?:ferais|feriez)[- ](?:tu|vous)\b|"
                             r"\b(?:vendr|achèter|acheter|garder|investir|placer|conserver)(?:ais|iez)[- ](?:tu|vous)\b"),
    ("advice", "suis-je mieux de", rf"\b(?:suis[- ]je|je\s+suis|serais[- ]je|chu|chus|j'suis)(?:[- ](?:tu|ti))?\s+mieux\s+"
                                   rf"d(?:e\s+|')(?:{_MOVE_FR}|tout)\b"),
    ("advice", "vaut la peine", r"\bvaut(?:[- ](?:il|tu|ti))?\s+la\s+peine\s+d'(?:acheter|investir|placer|garder|conserver|"
                                r"vendre)\b"),
    ("size", "le bon pourcentage", r"\b(?:meilleur|meilleure|meilleurs|meilleures|bon|bonne|juste|optimal|optimale|idéal|"
                                   r"idéale)\s+(?:\w+\s+)?(?:pourcentage|montant|taille|proportion|part|allocation|"
                                   r"répartition|portefeuille|placement|action)s?\b|"
                                   r"\bquel(?:le)?s?\s+(?:\w+\s+)?(?:pourcentage|montant|taille|proportion)\b[^?.!]{0,80}?"
                                   r"\b(?:dois|devrais|faut|conseill\w*)\b"),
    ("size", "c'est sécuritaire", r"\b(?:c'est|est-ce|est-il|serait-ce|ce\s+serait)\s+(?:\w+\s+){0,2}?(?:sécuritaire|sûr|"
                                  r"prudent|raisonnable|une\s+bonne\s+idée|un\s+bon\s+(?:achat|placement))\b|"
                                  r"\bsécuritaire\b"),
    ("size", "c'est correct de", r"\b(?:c'est|est-ce|est-il|serait-ce|ce\s+serait|ce\s+sera)\s+(?:\w+\s+){0,2}?(?:correct|"
                                 r"correcte|acceptable|ok|okay|permis|autorisé)\s+d(?:e\s+|')(?:avoir|mettre|garder|conserver|"
                                 r"détenir|placer|acheter|vendre|investir|liquider)\b"),
    # the future tense of a move ("vaudra", "atteindra-t-il") counts like "va-t-il baisser" (lane ev2)
    ("forecast", "va-t-il baisser", r"\b(?:va|vont)(?:-t-|-|\s+)(?:il|elle|ils|elles)?\s*(?:\w+\s+)?(?:baisser|monter|chuter|"
                                    r"remonter|s'effondrer|grimper|continuer|empirer|atteindre|dépasser|valoir|tomber|"
                                    r"rebondir|exploser|doubler|reculer|plonger)\b|\bprédi\w*\b|\bprévision\w*\b|"
                                    r"\b(?:vaud|atteind|baisse|monte|chute|grimpe|tombe|s'effondre|rebondi|remonte|dépasse|"
                                    r"double|recule|plonge)r(?:a|ont)\b"),
)
_COMPILED = tuple((kind, name, re.compile(rx, re.I)) for kind, name, rx in RULES)
_IF = re.compile(r"\b(?:if|what\s+if|suppose|imagine|et\s+si|si)\b|\bin\s+(?:this|the)\s+(?:history|replay)\b", re.I)
# A forecast counts only in a sentence that asks and is no what-if: "everyone says NVIDIA will keep going up." is no
# request, and "what will happen if the tariff war flares up?" is the product.
_ASKED = ("will it fall", "going to", "va-t-il baisser", "the odds")
_FRAMED = ("hold or sell",)              # any sentence, unless it is a what-if or a replay

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s"})
_B64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


SCAN_CHARS = 5000                # longer than any question the navigator reads (1,500) or the input guardrail checks


def _normal(text: str) -> str:
    t = unicodedata.normalize("NFC", str(text or "")[:SCAN_CHARS]).replace("’", "'").replace("‘", "'").replace("\\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def _deleet(text: str) -> str:
    """Words that mix letters with 0/1/3/4/5/7/8/@/$ read as letters ("5h0uld" -> "should"); a lone 1 between words
    reads as "i". Numbers ("40 %", "2022") stay as they are."""
    words = []
    for w in text.split(" "):
        core = w.strip(".,;:!?()\"'")
        if re.search(r"[a-z]", core, re.I) and re.search(r"[0-9@$]", core):
            w = w.translate(_LEET)
        elif core == "1":
            w = w.replace("1", "i")
        words.append(w)
    return " ".join(words)


def _decoded(text: str) -> list:
    """Plain-text readings of any base64 run in the question (16+ characters that decode to printable ASCII)."""
    out = []
    for run in _B64.findall(text):
        try:
            raw = base64.b64decode(run + "=" * (-len(run) % 4), validate=True).decode("ascii")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if raw.strip() and all(32 <= ord(c) < 127 for c in raw):
            out.append(_normal(raw))
    return out


def _retyped(text: str) -> str:
    """Common misspellings read as the word they stand for (_TYPOS: "shud i sel" -> "should i sell")."""
    words = []
    for w in text.split(" "):
        core = w.strip(".,;:!?()\"'")
        fix = _TYPOS.get(core.lower())
        words.append(w.replace(core, fix, 1) if core and fix else w)
    return " ".join(words)


def _readings(text: str) -> list:
    t = _normal(text)
    seen = []
    for v in (t, _deleet(t), _retyped(_deleet(t)), *_decoded(t)):
        if v and v not in seen:
            seen.append(v)
    return seen


_ASKING = re.compile(r"^\s*(?:and\s+|so\s+|but\s+|ok\s+|okay\s+)?(?:will|is|are|am|what|when|how|do|does|can|could|"
                     r"would|should|tell|predict|va|vont|est-ce)\b", re.I)


def _questions(text: str) -> list:
    """The sentences that ask: those ending with a question mark, and those opening with a question word ("Will NVIDIA
    fall next year" with no mark). "But everyone says NVIDIA will keep going up." asks nothing."""
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", text) if p.strip()]
    return [p for p in parts if p.endswith("?") or _ASKING.search(p)]


def screen(text) -> dict:
    """{"ok": True, ...} for a question EPICENTRE can replay; else ok False, the kind and rule that matched, and the one
    fixed sentence the page shows (see _ASKED for the forecast rules)."""
    for t in _readings(text):
        for kind, name, rx in _COMPILED:
            if name in _ASKED:
                hit = any(rx.search(q) and not _IF.search(q) for q in _questions(t))
            elif name in _FRAMED:
                hit = any(rx.search(q) and not _IF.search(q) for q in re.split(r"(?<=[.?!])\s+", t))
            else:
                hit = bool(rx.search(t))
            if hit:
                return {"ok": False, "kind": kind, "rule": name, "message": ADVICE_STOP}
    return {"ok": True, "kind": None, "rule": None, "message": None}


def validate_question(text) -> dict:
    """{"ok", "message"} (lane b4's entry point, kept): the gate's verdict and its one sentence."""
    s = screen(text)
    return {"ok": s["ok"], "message": s["message"]}


# ---- the reframe (controller ruling, Sun 2026-11-15; lane ev2) ----
# A question that asks for approval of a move it names ("Is 25 % Tesla reasonable for me?", "Ought I to put more into
# gold?", "Devrais-je augmenter ma part en tech ?") is not stopped: the replay answers it against the limits the investor
# set. It is reframed instead: pipeline._advice_gate puts reframe {reason} on the Result, the page shows REFRAME_LINE
# above the verdict, and the receipt (verify.py) names a yes / no answer like an advice word. screen() is unchanged.
REFRAME_LINE = ("EPICENTRE can't tell you whether a move is right for you. Here is what it already did against the "
                "limits you set.")
RIGHT_FOR_ME, WHETHER_TO, BEST_SIZE = ("asks whether a move or a size is right for you", "asks whether to make a move",
                                       "asks for the best size")
BETTER_FOR_ME = "asks whether a move would be better for you"   # "Would adding 20 % SPY improve my diversification?"
REFRAME_REASONS = (RIGHT_FOR_ME, WHETHER_TO, BEST_SIZE, BETTER_FOR_ME)
_JUDGED = (r"(?:ok|okay|fine|alright|acceptable|reasonable|sensible|prudent|correct|safe|wise|smart|"
           r"a\s+good\s+(?:idea|move|bet|plan)|too\s+(?:much|little|risky|aggressive|high|big|concentrated|heavy))")
_FOR_ME = (r"\bfor\s+(?:me|us|my\s+(?:age|situation|profile|goals?|retirement|horizon|family|floor|limits?)|"
           r"someone\s+(?:like\s+me|my\s+age))\b")
_APPROVAL = tuple((reason, re.compile(rx, re.I)) for reason, rx in (
    (RIGHT_FOR_ME, rf"\b(?:is|are|am|would|will)\s+(?:\S+\s+){{0,10}}?{_JUDGED}\b[^?.!]{{0,40}}?{_FOR_ME}"),
    (RIGHT_FOR_ME, rf"\b(?:is|are|would|will)\s+(?:\S+\s+){{0,8}}?\d+(?:[.,]\d+)?\s*%(?:\s+\S+){{0,6}}?\s+{_JUDGED}\b"),
    (RIGHT_FOR_ME, r"\b(?:am\s+i|are\s+we|would\s+i\s+be|will\s+i\s+be)\s+(?:ok|okay|fine|alright|safe)\s+"
                   r"(?:with|if|putting|holding|having|keeping)\b"),
    (WHETHER_TO, rf"\b(?:should|ought|shall|must)\s+(?:i|we)\s+(?:(?:to|still|just|really|also|now|then|actually)\s+)?"
                 rf"{_ACT}\b"),
    (WHETHER_TO, r"\b(?:devrais|dois|devrai|devrions|devons)[- ](?:t-)?(?:je|nous)\b|"
                 r"\best[- ]ce\s+que\s+(?:je|nous)\s+(?:devrais|dois|devrions|devons)\b|\bje\s+(?:devrais|dois)[- ](?:tu|ti)\b|"
                 r"\bfaudrait[- ]il\s+que\s+je\b"),
    (BEST_SIZE, r"\b(?:optimal|optimum|ideal|best|right|correct|perfect|suitable|appropriate)\s+(?:\w+\s+)?(?:%|percent|"
                r"percentage|share|allocation|weight|weighting|amount|size|mix|split|proportion|balance)(?!\w)"),
    (BEST_SIZE, r"\b(?:pourcentage|proportion|part|allocation|répartition|montant)\s+(?:\w+\s+){0,2}?(?:optimal|optimale|"
                r"idéal|idéale|juste)\b|\b(?:meilleur|meilleure|bon|bonne)\s+(?:pourcentage|proportion|répartition|montant)\b"),
))
# French "c'est-tu raisonnable ?" counts only about a move: a size, a move verb or "pour moi" in the same sentence
_JUDGED_FR = re.compile(r"\b(?:c'est|est-ce|ce\s+serait|serait-ce|ça\s+serait)(?:[- ](?:tu|ti))?\s*(?:\w+\s+){0,2}?"
                        r"(?:raisonnable|correct|correcte|ok|okay|acceptable|prudent|sécuritaire|sûr|sage|"
                        r"une\s+bonne\s+idée|trop\s+(?:risqué|risquée|agressif|agressive|élevé|élevée|gros|grosse))\b", re.I)
_MOVE_CONTEXT_FR = re.compile(r"\d\s*%|\bpour\s+(?:moi|nous|mon\s+âge)\b|\b(?:mettre|avoir|garder|acheter|vendre|investir|"
                              r"placer|détenir)\b", re.I)


# A yes / no evaluation of the investor's own move (controller ruling, Sun 2026-11-15): the question opens on would / does
# / is (after an optional "if …," clause) with a move as its subject; "How would adding X change my mix?" is open.
_MOVING = (r"(?:adding|moving|switching|selling|buying|putting|holding|replacing|swapping|trimming|cutting|increasing|"
           r"reducing|raising|lowering|going|shifting|rebalancing|keeping|dropping|dumping|investing|allocating|doubling|"
           r"halving)")
_LEAD = (r"^\W*(?:(?:what\s+if|if|when|once|after|suppose)\b[^?]{0,80}?[,—–;:]\s*)?"
         r"(?:(?:so|and|but|ok|okay|then|also|honestly)\s*,?\s+)?")
_SUBJ_MOVE = (rf"(?:(?:it|this|that)\b|(?:\S+\s+){{0,3}}?(?:{_MOVING}\b|\d+(?:[.,]\d+)?\s*%|(?:this|that|the|my)\s+"
              rf"(?:move|change|swap|switch|trade|plan|idea)\b))")
_BETTER_EN = tuple(re.compile(rx, re.I) for rx in (
    rf"{_LEAD}(?:would|will|could|does|do|might)\s+{_SUBJ_MOVE}[^?]{{0,60}}?\b(?:improve|help|hurt|harm|worsen|benefit|"
    rf"strengthen|weaken|fix|reduce|lower|increase|boost|balance|diversify)\w*\s+(?:my|our)\b",
    rf"{_LEAD}(?:would|will|could|is|are)\s+{_SUBJ_MOVE}[^?]{{0,60}}?\b(?:be\s+)?(?:better|worse|smarter|"
    rf"an?\s+(?:improvement|upgrade|mistake|error))\b",
    rf"{_LEAD}(?:would|does|do|will)\s+it\s+make\s+sense\s+(?:for\s+(?:me|us)\s+)?to\s+{_ACT}\b",
))
_BETTER_FR = tuple(re.compile(rx, re.I) for rx in (
    r"\best[- ]ce\s+qu(?:e|')\s*(?:\S+\s+){0,8}?(?:améliorer|aider|renforcer|diversifier|nuir|réduir)(?:ait|aient|a|ont)\b",
    r"\b(?:améliorer|aider|renforcer|diversifier|nuir|réduir)(?:ait|a)[- ](?:t-)?(?:il|elle)\b",
    r"\b(?:serait|sera|est)(?:[- ](?:ce|il|elle))?\s+(?:\S+\s+){0,3}?(?:mieux|meilleur|meilleure|préférable)\s+pour\s+"
    r"(?:moi|nous|mon|ma|mes)\b",
))
_MOVE_FR_NAMED = re.compile(r"\d\s*%|\b(?:ajout\w*|vend\w*|achet\w*|mettre|mets|passer|rempla\w*|augment\w*|rédui\w*|"
                            r"diminu\w*|déplac\w*)\b|\bce\s+(?:changement|mouvement)\b", re.I)


def approval_seeking(text):
    """Why the question asks for approval of a move (one of REFRAME_REASONS), else None. Never stops anything: it is
    read only on a question screen() let through, and only in a sentence that asks."""
    for t in _readings(text):
        for q in _questions(t):
            for reason, rx in _APPROVAL:
                if rx.search(q):
                    return reason
            if _JUDGED_FR.search(q) and _MOVE_CONTEXT_FR.search(q):
                return RIGHT_FOR_ME
            if any(rx.search(q) for rx in _BETTER_EN) or (
                    any(rx.search(q) for rx in _BETTER_FR) and _MOVE_FR_NAMED.search(q)):
                return BETTER_FOR_ME
    return None
