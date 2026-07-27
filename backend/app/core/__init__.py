"""
TravelMind Agent — Core Abstractions
Base classes for all provider types: LLM, Vision, Maps, Weather.
Phase 2+ will implement concrete providers against these interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers (DeepSeek)."""

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Send a chat completion request and return the response text."""
        ...

    @abstractmethod
    async def chat_stream(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> AsyncIterator[str]:
        """Send a streaming chat completion request."""
        ...

    @abstractmethod
    async def chat_structured(
        self,
        messages: List[Dict[str, str]],
        output_schema: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a chat request and return structured JSON output."""
        ...


class BaseVisionProvider(ABC):
    """Abstract base for vision providers (Kimi k2.6)."""

    @abstractmethod
    async def analyze_image(
        self, image_url: str, prompt: str
    ) -> Dict[str, Any]:
        """Analyze an image and return structured results."""
        ...


class BaseMapProvider(ABC):
    """Abstract base for map providers (Amap POI / routing / distance matrix)."""

    @abstractmethod
    async def search_places(
        self, query: str, city: Optional[str] = None, **kwargs
    ) -> List[Dict[str, Any]]:
        """Search for POIs near a location or city."""
        ...

    @abstractmethod
    async def get_place_detail(self, place_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific place."""
        ...


class BaseWeatherProvider(ABC):
    """Abstract base for weather providers (Open-Meteo)."""

    @abstractmethod
    async def get_forecast(
        self, lat: float, lon: float, days: int = 7
    ) -> Dict[str, Any]:
        """Get weather forecast for a location."""
        ...


__all__ = [
    "BaseLLMProvider",
    "BaseVisionProvider",
    "BaseMapProvider",
    "BaseWeatherProvider",
]
