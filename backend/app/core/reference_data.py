from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password, verify_password
from app.models.category import Category
from app.models.country import Country
from app.models.region import Region
from app.models.source import Source
from app.models.user import ROLE_ADMIN, User


DEFAULT_COUNTRIES = [
    ("India", "IN"),
    ("United States", "US"),
    ("China", "CN"),
    ("Russia", "RU"),
    ("United Kingdom", "GB"),
    ("France", "FR"),
    ("Pakistan", "PK"),
    ("Israel", "IL"),
    ("Japan", "JP"),
    ("Global", "GL"),
]

DEFAULT_REGIONS = [
    "Asia",
    "Europe",
    "Middle East",
    "North America",
    "South Asia",
    "Indo-Pacific",
    "Global",
]

DEFAULT_CATEGORIES = [
    ("Air", "air", "Air defense and aerospace systems."),
    ("Naval", "naval", "Naval operations, fleets, and maritime security."),
    ("Land", "land", "Ground force operations and land systems."),
    ("Defense Technology", "defense-technology", "Science, technology, and modernization programs."),
    ("Drones", "drones", "Unmanned systems and aerial surveillance."),
    ("Space", "space", "Space and satellite military capabilities."),
    ("Cyber", "cyber", "Cyber defense, attacks, and information warfare."),
    ("Procurement", "procurement", "Defense acquisitions and procurement activity."),
    ("Military Exercises", "military-exercises", "Exercises, drills, and joint operations."),
    ("Geopolitics", "geopolitics", "Strategic, diplomatic, and geopolitical developments."),
]

DEFAULT_SOURCES = [
    (
        "Reuters Defense",
        "https://www.reuters.com/world/",
        # Reuters has no public RSS feed; this Google News query is limited to reuters.com.
        "https://news.google.com/rss/search?q=site:reuters.com+(military+OR+defense+OR+missile+OR+army+OR+navy+OR+drone+OR+war)+when:2d&hl=en-US&gl=US&ceid=US:en",
        "Global",
        "Global",
        "wire",
        "en",
        96,
        180,
    ),
    (
        "BBC World",
        "https://www.bbc.com/news/world",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "United Kingdom",
        "Europe",
        "newsroom",
        "en",
        92,
        180,
    ),
    (
        "The Diplomat",
        "https://thediplomat.com/",
        "https://thediplomat.com/feed/",
        "Global",
        "Indo-Pacific",
        "analysis",
        "en",
        90,
        240,
    ),
    (
        "Defense News",
        "https://www.defensenews.com/",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "United States",
        "North America",
        "defense",
        "en",
        94,
        180,
    ),
    (
        "Al Jazeera World",
        "https://www.aljazeera.com/",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "Global",
        "Global",
        "newsroom",
        "en",
        91,
        240,
    ),
    (
        "Army Recognition",
        "https://www.armyrecognition.com/",
        "https://www.armyrecognition.com/rss.xml",
        "Global",
        "Global",
        "defense",
        "en",
        88,
        360,
    ),
]


def ensure_reference_data(db: Session) -> None:
    for name, code in DEFAULT_COUNTRIES:
        existing = db.query(Country).filter(Country.name == name).first()
        if existing is None:
            db.add(Country(name=name, code=code, is_active=True))

    for name in DEFAULT_REGIONS:
        existing = db.query(Region).filter(Region.name == name).first()
        if existing is None:
            db.add(Region(name=name, is_active=True))

    for name, slug, description in DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(Category.name == name).first()
        if existing is None:
            db.add(Category(name=name, slug=slug, description=description, is_active=True))

    db.flush()

    country_by_name = {
        country.name: country.id
        for country in db.query(Country).all()
    }
    region_by_name = {
        region.name: region.id
        for region in db.query(Region).all()
    }

    for (
        name,
        website_url,
        feed_url,
        country_name,
        region_name,
        source_type,
        language,
        reliability_score,
        collection_frequency,
    ) in DEFAULT_SOURCES:
        existing = db.query(Source).filter(Source.name == name).first()
        if existing is None:
            db.add(
                Source(
                    name=name,
                    website_url=website_url,
                    feed_url=feed_url,
                    country_id=country_by_name.get(country_name),
                    region_id=region_by_name.get(region_name),
                    source_type=source_type,
                    language=language,
                    reliability_score=reliability_score,
                    is_active=True,
                    collection_frequency=collection_frequency,
                )
            )

    ensure_admin_user(db)

    db.commit()


def ensure_admin_user(db: Session) -> None:
    # ADMIN_PASSWORD is the source of truth: setting it creates the admin or resets its password on startup.
    if not settings.admin_password:
        return

    admin = db.query(User).filter(User.email == settings.admin_email).first()
    if admin is None:
        db.add(
            User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                display_name="Defense Brief Admin",
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
    elif not verify_password(settings.admin_password, admin.password_hash):
        admin.password_hash = hash_password(settings.admin_password)
