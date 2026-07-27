"""
TravelMind Agent — SQLAlchemy ORM Models (8 tables)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    JSON,
    ARRAY,
    String,
    Text,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.connection import Base


def gen_uuid():
    return str(uuid.uuid4())


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── User ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(String(255), unique=True, nullable=True, index=True)
    device_id = Column(String(64), unique=True, nullable=True, index=True)
    is_anonymous = Column(Boolean, default=True)
    nickname = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=now_utc)
    last_active_at = Column(DateTime, default=now_utc)

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    recommendation_history = relationship("RecommendationHistory", back_populates="user")
    itineraries = relationship("Itinerary", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")


# ── UserProfile ───────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, unique=True)
    preferred_tags = Column(ARRAY(String), default=list)         # ["摄影", "美食", "历史"]
    travel_style = Column(String(50), nullable=True)              # "休闲" / "特种兵" / "亲子"
    budget_level = Column(String(20), nullable=True)              # "经济" / "舒适" / "奢华"
    preferred_duration = Column(Integer, nullable=True)           # days
    avoid_tags = Column(ARRAY(String), default=list)              # ["拥挤", "爬山"]
    raw_extraction = Column(JSON, nullable=True)                  # full LLM output
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)

    user = relationship("User", back_populates="profile")


# ── Attraction ────────────────────────────────────────

class Attraction(Base):
    __tablename__ = "attractions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False, index=True)
    name_en = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False, index=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    description_source = Column(String(50), nullable=True)     # "wikipedia" / "amap" / "ai"
    image_urls = Column(ARRAY(Text), default=list)
    price_level = Column(Integer, nullable=True)               # 1-5
    best_time = Column(String(100), nullable=True)              # "春季" / "全年" / "10-12月"
    suitable_for = Column(ARRAY(String), default=list)          # ["情侣", "亲子", "摄影"]
    opening_hours = Column(String(255), nullable=True)
    data_source = Column(String(50), nullable=True)            # "wikidata" / "amap" / "combined"
    source_id = Column(String(255), nullable=True)              # external ID
    confidence = Column(Float, default=1.0)                     # data reliability 0-1
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)

    tags = relationship("AttractionTag", back_populates="attraction")


# ── AttractionTag ─────────────────────────────────────

class AttractionTag(Base):
    __tablename__ = "attraction_tags"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    attraction_id = Column(UUID(as_uuid=False), ForeignKey("attractions.id"), nullable=False)
    tag = Column(String(50), nullable=False, index=True)          # "摄影", "美食", "历史", etc.

    attraction = relationship("Attraction", back_populates="tags")


# ── TrendData ─────────────────────────────────────────

class TrendData(Base):
    __tablename__ = "trend_data"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    city = Column(String(100), nullable=False, index=True)
    place_name = Column(String(255), nullable=True)
    tag = Column(String(50), nullable=True)                      # trending category
    heat_score = Column(Float, default=0.0)                      # 0-100
    rank = Column(Integer, nullable=True)
    source = Column(String(100), nullable=True)                  # "ctrip_hotlist" / "xiaohongshu" ...
    fetched_at = Column(DateTime, default=now_utc)


# ── RecommendationHistory ─────────────────────────────

class RecommendationHistory(Base):
    __tablename__ = "recommendation_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    query_input = Column(Text, nullable=True)
    results = Column(JSON, nullable=True)                        # [{place_id, score, factors}, ...]
    scores_detail = Column(JSON, nullable=True)                  # full scoring breakdown
    created_at = Column(DateTime, default=now_utc)

    user = relationship("User", back_populates="recommendation_history")


# ── Itinerary ─────────────────────────────────────────

class Itinerary(Base):
    __tablename__ = "itineraries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=True)
    days = Column(Integer, nullable=False)
    plan = Column(JSON, nullable=False)                          # full day-by-day plan
    weather_snapshot = Column(JSON, nullable=True)               # weather at planning time
    validation_report = Column(JSON, nullable=True)              # Phase 1 validation data
    profile_snapshot = Column(JSON, nullable=True)               # user slots at generation time
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)

    user = relationship("User", back_populates="itineraries")


# ── ItineraryVersion (Phase 8.3) ──────────────────────

class ItineraryVersion(Base):
    """Snapshot version chain for itinerary changes.

    Each time an itinerary is regenerated (day-level or full), a new version
    is created with the full plan JSON at that point. Restore creates a NEW
    version (copy-on-restore).
    """
    __tablename__ = "itinerary_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    itinerary_id = Column(
        UUID(as_uuid=False),
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    plan = Column(JSON, nullable=False)                              # full TravelItinerary snapshot
    change_description = Column(String(500), nullable=True)          # e.g. "重新安排第2天：太赶了"
    created_at = Column(DateTime, default=now_utc)

    __table_args__ = (
        UniqueConstraint("itinerary_id", "version_number", name="uq_version_per_itinerary"),
    )


# ── Feedback ──────────────────────────────────────────

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    target_type = Column(String(50), nullable=False)             # "recommendation" / "itinerary" / "chat"
    target_id = Column(UUID(as_uuid=False), nullable=True)
    rating = Column(Integer, nullable=True)                      # 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_utc)

    user = relationship("User", back_populates="feedbacks")


# ── Favorite ──────────────────────────────────────────

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)             # "attraction" | "itinerary"
    target_id = Column(String(255), nullable=False)              # attraction name or itinerary UUID
    created_at = Column(DateTime, default=now_utc)

    user = relationship("User", back_populates="favorites")
