"""
Tool: Hacker News (Algolia API)
Gratuita, sem chave de API, sem rate limit agressivo.
Docs: https://hn.algolia.com/api
"""
from __future__ import annotations

from typing import List

import requests

from .rss_source import Item

BASE_URL = "https://hn.algolia.com/api/v1/search"


def fetch_hn(query: str, max_results: int = 15, min_points: int = 20) -> List[Item]:
    """Busca histórias no HN relevantes para uma query (ex: um tema da watchlist)."""
    params = {
        "query": query,
        "tags": "story",
        "hitsPerPage": max_results,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[hn] erro na busca '{query}': {exc}")
        return []

    items: List[Item] = []
    for hit in data.get("hits", []):
        if (hit.get("points") or 0) < min_points:
            continue
        items.append(
            Item(
                title=hit.get("title") or "(sem título)",
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                source="Hacker News",
                published=hit.get("created_at", ""),
                summary=f"{hit.get('points', 0)} pontos, {hit.get('num_comments', 0)} comentários",
                tags=[query],
            )
        )
    return items


if __name__ == "__main__":
    results = fetch_hn("LangGraph", max_results=5)
    for i in results:
        print(f"- {i.title} ({i.summary})")
