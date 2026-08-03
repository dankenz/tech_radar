"""
Tool: RSS
Busca itens em feeds RSS/Atom curados (config/rss_sources.yaml).
Fonte primária para blogs de engenharia — gratuita, sem rate limit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

import feedparser
import yaml


@dataclass
class Item:
    title: str
    url: str
    source: str
    published: str
    summary: str
    tags: List[str] = field(default_factory=list)


def load_sources(config_path: str) -> list[dict]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def fetch_rss(config_path: str, max_items_per_source: int = 10) -> List[Item]:
    """Busca os itens mais recentes de cada feed configurado.

    Falha em um feed individual não derruba os outros — só é logada e pulada,
    já que blogs mudam de URL/estrutura com frequência.
    """
    items: List[Item] = []
    for source in load_sources(config_path):
        try:
            parsed = feedparser.parse(source["url"])
            if parsed.bozo and not parsed.entries:
                print(f"[rss] aviso: falha ao ler '{source['name']}' ({source['url']})")
                continue

            for entry in parsed.entries[:max_items_per_source]:
                items.append(
                    Item(
                        title=entry.get("title", "(sem título)"),
                        url=entry.get("link", ""),
                        source=source["name"],
                        published=entry.get("published", entry.get("updated", "")),
                        summary=entry.get("summary", "")[:500],
                        tags=source.get("tags", []),
                    )
                )
        except Exception as exc:  # noqa: BLE001 - blog RSS é imprevisível, seguimos em frente
            print(f"[rss] erro em '{source.get('name', '?')}': {exc}")
            continue

    return items


if __name__ == "__main__":
    # Teste manual rápido: python -m tools.rss_source
    results = fetch_rss("config/rss_sources.yaml", max_items_per_source=3)
    print(f"{len(results)} itens coletados")
    for i in results[:5]:
        print(f"- [{i.source}] {i.title}")
