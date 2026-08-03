"""
Tool: GNews + NewsAPI
Cobrem rupturas de mercado / temas genéricos que a watchlist estratégica pede.
Ambas exigem chave de API — ver .env.example.

GNews:   https://gnews.io/docs/v4
NewsAPI: https://newsapi.org/docs
"""
from __future__ import annotations

import os
from typing import List

import requests

from .rss_source import Item

GNEWS_URL = "https://gnews.io/api/v4/search"
NEWSAPI_URL = "https://newsapi.org/v2/everything"


def fetch_gnews(query: str, api_key: str | None = None, max_results: int = 10) -> List[Item]:
    api_key = api_key or os.getenv("GNEWS_API_KEY")
    if not api_key:
        print("[gnews] GNEWS_API_KEY não configurada, pulando")
        return []

    params = {
        "q": query,
        "lang": "en",  # queries em NEWS_QUERIES sao em ingles; "pt" quase zerava os resultados
        "max": max_results,
        "apikey": api_key,
    }
    try:
        resp = requests.get(GNEWS_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[gnews] erro na busca '{query}': {exc}")
        return []

    return [
        Item(
            title=a.get("title", "(sem título)"),
            url=a.get("url", ""),
            source=f"GNews · {a.get('source', {}).get('name', '')}",
            published=a.get("publishedAt", ""),
            summary=(a.get("description") or "")[:500],
            tags=[query],
        )
        for a in data.get("articles", [])
    ]


def fetch_newsapi(query: str, api_key: str | None = None, max_results: int = 10) -> List[Item]:
    api_key = api_key or os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("[newsapi] NEWSAPI_KEY não configurada, pulando")
        return []

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": max_results,
        "apiKey": api_key,
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[newsapi] erro na busca '{query}': {exc}")
        return []

    return [
        Item(
            title=a.get("title", "(sem título)"),
            url=a.get("url", ""),
            source=f"NewsAPI · {a.get('source', {}).get('name', '')}",
            published=a.get("publishedAt", ""),
            summary=(a.get("description") or "")[:500],
            tags=[query],
        )
        for a in data.get("articles", [])
    ]


if __name__ == "__main__":
    results = fetch_gnews("agentes de IA") + fetch_newsapi("AI agents")
    for i in results:
        print(f"- [{i.source}] {i.title}")
