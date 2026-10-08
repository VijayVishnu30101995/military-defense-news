import re

from app.config import settings


_SPORTS_TERMS = re.compile(
    r"\b(?:athletics|badminton|baseball|basketball|boxing|cricket|"
    r"formula\s*1|f1|football|golf|hockey|ipl|mlb|nba|nfl|nhl|olympics|"
    r"rugby|soccer|tennis|tournament|uefa|ufc|volleyball|world cup)\b",
    re.IGNORECASE,
)
_DEFENSE_TERMS = re.compile(
    r"\b(?:air force|airstrike|armed forces|ballistic missile|"
    r"combat|defen[cs]e|ministry of defense|military|missile|nato|"
    r"pentagon|rocket|soldier|troops|war|weapon)\b",
    re.IGNORECASE,
)


def is_sports_story(title: str, description: str | None = None) -> bool:
    text = f"{title} {description or ''}"
    return bool(_SPORTS_TERMS.search(text) and not _DEFENSE_TERMS.search(text))


# Entertainment and sport vocabulary that disqualifies a story outright, however
# much defense vocabulary it also carries ("military service exemption for athletes").
_ALWAYS_OFF_TOPIC = re.compile(
    r"\b(?:athletes?|k-?pop|celebrit(?:y|ies)|box office|red carpet|fashion week)\b",
    re.IGNORECASE,
)


# Unambiguous defense vocabulary. A single core term is enough to carry a story.
# Multi-word alternatives come first so the longer phrase wins the match.
_CORE_TERMS = re.compile(
    r"\b(?:"
    # forces, institutions, organisations
    r"ministry of defen[cs]e|department of defen[cs]e|defen[cs]e (?:ministry|minister|secretary|chief|department|budget|contract|industry|spending|procurement|pact|deal|agreement|staff|cooperation)|"
    r"armed forces|air force|space force|coast guard|national guard|special forces|paramilitary|"
    r"pentagon|nato|iaea|military|militar(?:ies|ization|isation)|army|armies|navy|naval|marines|"
    r"soldiers?|troops?|servicemembers?|servicemen|admirals?|brigade|battalion|regiment|"
    # Officer ranks. "general" alone is excluded deliberately: general election, general
    # public, in general. Only the qualified military forms count.
    r"brigadiers?|(?:lieutenant|major|army|military|syrian|russian|retired) generals?|general staff|"
    r"troop deployment|mobili[sz]ation|conscription|"
    # platforms and weapons
    r"aircraft carriers?|carrier strike group|ballistic missile submarine|nuclear submarine|"
    r"warships?|destroyers?|frigates?|corvettes?|submarines?|gunships?|"
    r"fighter jets?|fighter aircraft|warplanes?|bombers?|"
    r"ballistic|hypersonic|icbm|cruise missile|anti-?ship missile|surface-to-air|"
    r"missiles?|warheads?|artillery|howitzers?|munitions?|ammunition|loitering munitions?|"
    r"projectiles?|"
    r"air defen[cs]e|missile defen[cs]e|anti-?aircraft|"
    # Military aircraft and UAV designators: F-35, B-21, P-8, MQ-9, YFQ-48, MH-139, KC-46.
    # The prefix list is explicit so civilian strings like "COVID-19" cannot match.
    r"(?:f/a|fa|f|a|b|c|e|p|t|u|v|x|s|h|ah|ch|mh|uh|oh|kc|ec|rc|mq|rq|yfq|cq|sr|ea|av|cv|mv)-\d{1,3}[a-z]?|"
    r"su-?(?:24|25|27|30|34|35|57)|mig-?\d{1,2}|j-?(?:10|16|20|31|35)|"
    r"gripen|rafale|eurofighter|tejas|awacs|"
    # Defense primes: a story naming one is almost always about defense business.
    r"northrop grumman|lockheed martin|raytheon|bae systems|general dynamics|general atomics|"
    r"rheinmetall|dassault|leonardo|thales|rostec|almaz-antey|hanwha|"
    r"airbus defen[cs]e|boeing defen[cs]e|drdo|"
    # Intelligence and surveillance platforms
    r"sigint|elint|electronic intelligence|early warning aircraft|airborne early warning|"
    r"collaborative combat aircraft|"
    # operations and conflict
    r"airstrikes?|air strikes?|drone strikes?|drone attacks?|missile strikes?|"
    # A strike is only a military strike when a combatant or a theatre is named;
    # bare "strikes" is just as often industrial action.
    r"(?:russian|ukrainian|israeli|iranian|american|u\.?s\.?|saudi|houthi|nato|military|retaliatory|deadly) strikes?|"
    r"strikes? on (?:ukraine|kyiv|gaza|iran|israel|lebanon|yemen|russia|syria|damascus|tehran|moscow)|"
    r"bombardment|shelling|military offensive|ground offensive|invasion|incursion|"
    r"ceasefire|cease-fire|armistice|frontline|front line|battlefield|"
    r"military (?:exercise|drill|base|operation|aid|spending|coup|intervention)|war games?|joint exercises?|"
    r"(?:ukraine|gaza|iraq|afghan|syrian|yemen|korean|civil|proxy) wars?|"
    r"prisoners? of war|prisoner-of-war|counter-?terroris[mt]|"
    # security and strategic
    r"espionage|spy chief|spy satellite|intelligence agency|reconnaissance|surveillance aircraft|"
    r"cyber ?(?:attack|warfare|defen[cs]e|espionage)|"
    r"military satellite|arms? (?:procurement|acquisition|embargo)|arms (?:deal|sale|race|control)|"
    r"taiwan strait|south china sea|line of control|"
    r"hamas|hezbollah|houthis?|idf"
    r")\b",
    re.IGNORECASE,
)

# Defense-leaning but used freely outside defense ("drone delivery", "price war",
# "tank of fuel"). Never enough on its own; needs corroboration to clear the bar.
_SUPPORTING_TERMS = re.compile(
    r"\b(?:"
    r"drones?|uavs?|unmanned|rockets?|radar|tanks?|armou?red|helicopters?|"
    r"nuclear|enrichment|weapons?|warfare|wartime|combat|wars?|"
    r"insurgen(?:t|ts|cy)|militants?|rebels?|conflict zone|bombing|"
    r"strikes? on|deployed|deployment|security forces"
    r")\b",
    re.IGNORECASE,
)

# Generic diplomacy/geopolitics vocabulary. Only meaningful alongside stronger signals.
_WEAK_TERMS = re.compile(
    r"\b(?:"
    r"sanctions?|embargo|export controls?|tensions?|standoff|escalation|"
    r"summit|treaty|alliances?|diplomac\w*|minister|talks|geopolitic\w*"
    r")\b",
    re.IGNORECASE,
)

# Phrases that borrow defense vocabulary for something else. These subtract, so a
# story cannot rescue itself merely by also matching a weak defense term.
_PENALTY_TERMS = re.compile(
    r"\b(?:"
    r"defen[cs]e (?:attorney|lawyer|counsel|team|rests)|"
    r"trade war|price war|culture war|bidding war|turf war|war of words|"
    r"star wars|war correspondent|think tanks?|"
    r"head coach|goalkeeper|striker|midfielder|quarterback|"
    r"movie|film|box office|netflix|album|fashion|"
    r"stock market|share price|quarterly earnings|"
    # Commodity and market coverage that borrows conflict vocabulary for context
    # ("pre-war rate", "Iran war boosts fuel markets").
    r"refining margins?|fuel markets?|oil flows?|oil prices?|crude prices?|"
    r"cargoes|sunflower oil|trade deficit|trade talks?|tariffs?"
    r")\b",
    re.IGNORECASE,
)

_CORE_WEIGHT = 30
_SUPPORTING_WEIGHT = 12
_WEAK_WEIGHT = 5
_PENALTY_WEIGHT = 40
# The headline is the most signal-dense text, so its matches count double.
_HEADLINE_MULTIPLIER = 2
# Body text is long enough that incidental mentions are common; weight it down.
_BODY_DIVISOR = 2


def score_defense_relevance(
    title: str,
    summary: str | None = None,
    body: str | None = None,
) -> int:
    """How strongly a story concerns defense, on a 0-100 scale.

    Core terms alone can carry a story; supporting terms cannot, which is what keeps
    "drone delivery startup" and "trade war" out of a defense feed.
    """
    headline = (title or "").lower()
    if _ALWAYS_OFF_TOPIC.search(headline) or _ALWAYS_OFF_TOPIC.search((summary or "").lower()):
        return 0

    def tally(text: str) -> int:
        return (
            len(_CORE_TERMS.findall(text)) * _CORE_WEIGHT
            + len(_SUPPORTING_TERMS.findall(text)) * _SUPPORTING_WEIGHT
            + len(_WEAK_TERMS.findall(text)) * _WEAK_WEIGHT
            - len(_PENALTY_TERMS.findall(text)) * _PENALTY_WEIGHT
        )

    score = tally(headline) * _HEADLINE_MULTIPLIER
    score += tally((summary or "").lower())
    if body:
        score += tally(body.lower()) // _BODY_DIVISOR

    return max(0, min(score, 100))


def is_defense_story(title: str, description: str | None = None) -> bool:
    """True when the story is about defense, security or armed conflict."""
    if is_sports_story(title, description):
        return False
    return score_defense_relevance(title, description) >= settings.relevance_threshold


def is_off_topic_story(title: str, description: str | None = None) -> bool:
    return not is_defense_story(title, description)
