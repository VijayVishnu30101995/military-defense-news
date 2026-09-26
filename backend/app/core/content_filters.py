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
