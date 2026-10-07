import re


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


# A story is only kept when it clearly concerns defense, security or armed conflict.
_DEFENSE_RELEVANCE = re.compile(
    r"\b(?:"
    # forces and organisations
    r"military|militar(?:y|ies|ization|isation)|armed forces|army|armies|navy|naval|air force|"
    r"marines?|coast guard|space force|national guard|special forces|paramilitary|"
    r"nato|pentagon|ministry of defen[cs]e|department of defen[cs]e|defen[cs]e (?:ministry|minister|secretary|chief|forces?|budget|contract|industry|spending|minister|department|force|staff|cooperation|pact|deal|agreement|procurement|systems?|technology)|"
    r"defen[cs]e news|"
    r"soldiers?|troops?|servicemembers?|servicemen|army commanders?|military commanders?|admirals?|brigade|battalion|regiment|"
    # weapons and platforms
    r"missiles?|warheads?|ballistic|hypersonic|rockets?|artillery|howitzers?|tanks?|armou?red|"
    r"fighter jets?|fighter aircraft|warplanes?|bombers?|helicopters?|gunships?|"
    r"warships?|destroyers?|frigates?|corvettes?|submarines?|aircraft carriers?|"
    r"drones?|uavs?|unmanned|loitering munitions?|"
    r"weapons?|arms (?:deal|sale|race|control|embargo|exports?)|munitions?|ammunition|"
    r"nuclear (?:weapons?|arsenal|deterrent|warheads?|test|submarine|missile)|"
    r"air defen[cs]e|missile defen[cs]e|radar|anti-?ship|anti-?aircraft|"
    r"f-?(?:16|22|35)|su-?(?:34|35|57)|j-?(?:20|35)|"
    # operations and conflict
    r"(?:russian|ukrainian|israeli|iranian|us|u\.s\.|american|saudi|houthi|missile|drone|air|military|deadly) strikes?|strikes? on (?:ukraine|kyiv|gaza|iran|israel|lebanon|yemen|russia|syria)|"
    r"iaea|nuclear (?:program(?:me)?|facilit(?:y|ies)|sites?|talks|deal|access|plant|power plant attack)|enrichment|"
    r"airstrikes?|air strikes?|bombing|bombardment|shelling|military offensive|ground offensive|invasion|incursion|"
    r"ceasefire|cease-fire|frontline|front line|battlefield|combat|warfare|wartime|"
    r"war|wars|conflict zone|insurgen(?:t|ts|cy)|militants?|rebels?|"
    r"military (?:exercise|drill|base|operation|aid|spending|coup)|joint exercises?|war games?|"
    r"troop deployment|mobili[sz]ation|conscription|"
    r"counter-?terroris[mt]|terror(?:ist|ism) attack|"
    # security and strategic
    r"cyber ?(?:attack|warfare|defen[cs]e|security|espionage)|"
    r"intelligence agency|espionage|spy satellite|reconnaissance|surveillance aircraft|"
    r"satellite launch|military satellite|"
    r"arms? (?:procurement|acquisition)|defen[cs]e procurement|"
    r"sanctions on russia|ukraine war|"
    r"taiwan strait|south china sea|line of control|"
    r"hamas|hezbollah|houthis?|idf"
    r")\b",
    re.IGNORECASE,
)

# Phrases that match the vocabulary above but are not about defense.
_NOT_DEFENSE = re.compile(
    r"\b(?:defen[cs]e (?:attorney|lawyer|counsel|team|rests)|"
    r"star wars|think tanks?|price war|trade war|culture war|bidding war|turf war|"
    r"head coach|goalkeeper|striker|midfielder|quarterback|"
    r"movie|film|box office|celebrity|netflix|album|fashion)\b",
    re.IGNORECASE,
)


# Entertainment and sport vocabulary that disqualifies a story even if it says "military".
_ALWAYS_OFF_TOPIC = re.compile(
    r"\b(?:athletes?|k-?pop|celebrit(?:y|ies)|box office|red carpet|fashion week)\b",
    re.IGNORECASE,
)


def is_defense_story(title: str, description: str | None = None) -> bool:
    """True when the story is about defense, security or armed conflict."""
    text = f"{title} {description or ''}"
    if _ALWAYS_OFF_TOPIC.search(text):
        return False
    if not _DEFENSE_RELEVANCE.search(text):
        return False
    # Negative phrases only veto a story that has no stronger defense signal.
    if _NOT_DEFENSE.search(text) and not _DEFENSE_TERMS.search(text):
        return False
    return not is_sports_story(title, description)


def is_off_topic_story(title: str, description: str | None = None) -> bool:
    return not is_defense_story(title, description)
