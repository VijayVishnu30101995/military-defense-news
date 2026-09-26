from app.core.content_filters import is_sports_story


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
