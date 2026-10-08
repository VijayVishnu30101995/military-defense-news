from app.config import settings
from app.core.content_filters import (
    is_defense_story,
    is_off_topic_story,
    is_sports_story,
    score_defense_relevance,
)


def test_filters_sports_news() -> None:
    assert is_sports_story(
        "Virat Kohli says he will retire from India cricket after 2027 World Cup"
    )
    assert is_sports_story(
        "England vs Spain: UEFA Nations League",
        "The teams meet in the football final.",
    )


def test_keeps_defense_news_even_when_it_mentions_sport() -> None:
    assert not is_sports_story(
        "Military uses football stadium as emergency shelter",
        "Troops have secured the site during the conflict.",
    )


def test_keeps_defense_news_without_sports_terms() -> None:
    assert not is_sports_story(
        "Iran expands missile programme amid regional tensions"
    )


def test_keeps_defense_and_conflict_news() -> None:
    for title in [
        "Pentagon names 4 directed-energy weapons for counter-drone program",
        "Russian drone attack kills two at Ukraine-Moldova border crossing",
        "Russian strikes on Ukraine's Kyiv kill at least two people",
        "Houthi attacks on southern Saudi Arabia reportedly injure dozens",
        "Navy christens new destroyer as shipbuilders miss delivery targets",
        "India test-fires hypersonic missile from Odisha coast",
        "IAEA warns over Iran nuclear access",
        "Former German spy chief arrested for espionage and treason",
    ]:
        assert is_defense_story(title), title


def test_rejects_general_news() -> None:
    for title in [
        "Flash floods fill the streets of a neighbourhood in central Morocco",
        "Canada's retaliatory tariffs on $20bn of US goods take effect",
        "Head coach Scaloni's emotional farewell to 'irreplaceable' Messi",
        "Three paintings worth $10m stolen from Renoir Museum",
        "Digital Asset Regulations in the Asia-Pacific",
        "Real Madrid vs Inter: Champions League preview",
        "Think tanks urge new approach to climate policy",
        "Defense attorney says client will not testify",
        "South Korea's military service exemption could be cut for athletes",
    ]:
        assert is_off_topic_story(title), title


def test_description_can_establish_defense_relevance() -> None:
    assert is_defense_story(
        "Leaders meet in Brussels",
        "Talks focus on NATO troop deployments along the eastern flank.",
    )


def test_rejects_non_military_uses_of_war() -> None:
    """Regression: these all used to pass because the veto was cancelled by the bare word "war"."""
    for title in [
        "US and China escalate trade war over tariffs",
        "Airlines deepen price war on transatlantic routes",
        "The culture war over school curriculums intensifies",
        "Amazon and Walmart in bidding war for retail startup",
        "Netflix orders new series about a war correspondent",
    ]:
        assert is_off_topic_story(title), title


def test_rejects_commodity_news_that_mentions_conflict() -> None:
    for title in [
        "Shell expects record refining margins as Iran war boosts fuel markets",
        "Gulf oil flows rise to average 81% of pre-war rate in September",
        "India-bound sunflower oil cargoes face cancellation amid delays",
    ]:
        assert is_off_topic_story(title), title


def test_supporting_terms_alone_are_not_enough() -> None:
    """A civilian story built on one defense-adjacent word must not qualify."""
    assert is_off_topic_story("Hospital drone delivery program launches in Rwanda")
    assert score_defense_relevance("Hospital drone delivery program launches in Rwanda") < (
        settings.relevance_threshold
    )


def test_recognises_military_aircraft_designators() -> None:
    for title in [
        "Northrop Grumman's YFQ-48 flies for the first time",
        "MH-139A Grey Wolf enters full-rate production",
        "The P-3 Orion airborne early warning aircraft has flown its last mission",
        "Spain picks Airbus A321 for new electronic intelligence aircraft",
    ]:
        assert is_defense_story(title), title


def test_aircraft_designator_pattern_ignores_civilian_strings() -> None:
    for title in [
        "COVID-19 cases rise across Europe",
        "Apple reports Q-3 earnings beat",
    ]:
        assert is_off_topic_story(title), title


def test_headline_outweighs_summary() -> None:
    in_headline = score_defense_relevance("Navy destroyer deployed", "Routine update.")
    in_summary = score_defense_relevance("Routine update", "Navy destroyer deployed.")
    assert in_headline > in_summary


def test_score_is_bounded() -> None:
    assert score_defense_relevance("") == 0
    dense = " ".join(["missile warship pentagon airstrike submarine"] * 20)
    assert 0 <= score_defense_relevance(dense) <= 100
