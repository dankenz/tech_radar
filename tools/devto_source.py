"""
Tool: dev.to
API pública, gratuita, sem chave obrigatória para leitura.
Docs: https://developers.forem.com/api
"""
from __future__ import annotations

from typing import List

import requests

from .rss_source import Item

BASE_URL = "https://dev.to/api/articles"


def fetch_devto(tag: str, max_results: int = 10) -> List[Item]:
    """Busca artigos do dev.to por tag (ex: 'machinelearning', 'kubernetes')."""
    params = {"tag": tag, "per_page": max_results, "top": 7}  # top=7 -> mais relevantes na última semana
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[devto] erro na busca '{tag}': {exc}")
        return []

    items: List[Item] = []
    for article in data:
        items.append(
            Item(
                title=article.get("title", "(sem título)"),
                url=article.get("url", ""),
                source="dev.to",
                published=article.get("published_at", ""),
                summary=article.get("description", "")[:500],
                tags=[tag],
            )
        )
    return items


if __name__ == "__main__":
    results = fetch_devto("machinelearning", max_results=5)
    for i in results:
        print(f"- {i.title}")
