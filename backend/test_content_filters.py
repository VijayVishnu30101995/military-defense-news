from app.core.content_filters import is_defense_story, is_off_topic_story, is_sports_story


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
