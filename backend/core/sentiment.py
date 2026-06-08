"""
Sentiment Analysis Module using Azure Text Analytics API.

Analyzes transcription text for emotional tone and confidence metrics.
Uses Azure Cognitive Services Language endpoint.

NOTA: Este módulo está integrado de forma experimental e será expandido no futuro
para fornecer insights emocionais detalhados nas auditorias.
"""

import logging
import os

logger = logging.getLogger(__name__)
from typing import Optional

import httpx
from utils.http_session import should_trust_env_proxies

AZURE_TEXT_ANALYTICS_ENDPOINT = os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT", "").strip().rstrip("/")
AZURE_TEXT_ANALYTICS_KEY = os.getenv("AZURE_TEXT_ANALYTICS_KEY", "").strip()


async def analyze_sentiment(text: str, language: str = "pt-BR") -> Optional[dict]:
    """
    Analyzes sentiment of the given text using Azure Text Analytics.

    Returns:
        dict with sentiment, confidenceScores, and per-sentence breakdown, or None on failure.
    """
    if not AZURE_TEXT_ANALYTICS_KEY or not AZURE_TEXT_ANALYTICS_ENDPOINT:
        logger.debug("Sentiment Analysis: Azure Text Analytics not configured, skipping.")
        return None

    url = f"{AZURE_TEXT_ANALYTICS_ENDPOINT}/text/analytics/v3.1/sentiment"

    body = {
        "documents": [
            {"id": "1", "language": language, "text": text}
        ]
    }

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_TEXT_ANALYTICS_KEY,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=should_trust_env_proxies()) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            result = response.json()

        if "documents" in result and len(result["documents"]) > 0:
            doc = result["documents"][0]

            sentences = []
            for sentence in doc.get("sentences", []):
                sentences.append({
                    "text": sentence.get("text", ""),
                    "sentiment": sentence.get("sentiment", "neutral"),
                    "confidenceScores": sentence.get("confidenceScores", {})
                })

            return {
                "overall": doc.get("sentiment", "neutral"),
                "confidenceScores": doc.get("confidenceScores", {}),
                "sentences": sentences
            }

        if "errors" in result and len(result["errors"]) > 0:
            logger.warning("Sentiment Analysis Error: %s", result["errors"])
            return None

        return None

    except Exception as error:
        logger.warning("Sentiment Analysis Exception: %s", error)
        return None


def format_sentiment_label(sentiment: str) -> str:
    """Translates Azure sentiment labels to Portuguese."""
    labels = {
        "positive": "Positivo",
        "negative": "Negativo",
        "neutral": "Neutro",
        "mixed": "Misto"
    }
    return labels.get(sentiment, sentiment.capitalize())


def get_sentiment_emoji(sentiment: str) -> str:
    """Compatibility helper without emoji usage."""
    return format_sentiment_label(sentiment)
