"""
Radar — Fase 1: agente curador (tool use).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from relevance import dedupe, diversify, load_profile, rank_items
from tools.devto_source import fetch_devto
from tools.hn_source import fetch_hn
from tools.news_source import fetch_gnews, fetch_newsapi
from tools.rss_source import fetch_rss

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
PROFILE_PATH = os.path.join(CONFIG_DIR, "profile.json")
RSS_CONFIG_PATH = os.path.join(CONFIG_DIR, "rss_sources.yaml")

DEVTO_TAGS = ["machinelearning", "mlops", "kubernetes", "computervision"]
HN_QUERIES = ["AI agents", "LangGraph", "feature store", "model serving"]
NEWS_QUERIES = ["AI agent framework", "MLOps", "market disruption AI"]


def collect_all():
    items = []
    print("Buscando RSS...")
    items += fetch_rss(RSS_CONFIG_PATH, max_items_per_source=8)
    print("Buscando Hacker News...")
    for q in HN_QUERIES:
        items += fetch_hn(q, max_results=8)
    print("Buscando dev.to...")
    for tag in DEVTO_TAGS:
        items += fetch_devto(tag, max_results=8)
    print("Buscando GNews/NewsAPI...")
    for q in NEWS_QUERIES:
        items += fetch_gnews(q, max_results=5)
        items += fetch_newsapi(q, max_results=5)
    return dedupe(items)


def main():
    load_dotenv()
    profile = load_profile(PROFILE_PATH)
    all_items = collect_all()
    print(f"\n{len(all_items)} itens unicos coletados.\n")

    counts = {}
    for i in all_items:
        counts[i.source] = counts.get(i.source, 0) + 1
    print("Itens coletados por fonte:")
    for source, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {source}")
    print()

    ranked = rank_items(all_items, profile, min_score=1.5)
    print(f"{len(ranked)} itens relevantes apos filtro.\n")
    diversified = diversify(ranked, max_per_source=3)
    print("=" * 70)
    print("DIGEST RADAR")
    print("=" * 70)
    for scored in diversified[:20]:
        item = scored.item
        print(f"\n[{scored.score:.1f}] {item.title}")
        print(f"  fonte: {item.source} | {item.published}")
        print(f"  {item.url}")
        for reason in scored.reasons[:3]:
            print(f"  - {reason}")


if __name__ == "__main__":
    main()
