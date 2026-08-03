"""
Fase 3 -- ponto de entrada. Pega os itens mais relevantes do pipeline da
Fase 1, roda o grafo (classificador + tutor + feedback) pra cada um, e
salva o profile.json atualizado no final.

Uso:
    python -m tutor.run_lesson
    python -m tutor.run_lesson --max 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from main import PROFILE_PATH, collect_all  # noqa: E402
from relevance import load_profile, rank_items  # noqa: E402
from tutor.graph import build_graph  # noqa: E402


def already_taught(url: str, profile: dict) -> bool:
    return any(entry.get("item_url") == url for entry in profile.get("feedback_log", []))


def save_profile(profile: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=3, help="quantos itens processar nessa rodada")
    args = parser.parse_args()

    load_dotenv()
    profile = load_profile(PROFILE_PATH)

    print("Coletando itens (pipeline da Fase 1)...")
    all_items = collect_all()
    ranked = rank_items(all_items, profile, min_score=1.5)

    candidates = [s.item for s in ranked if not already_taught(s.item.url, profile)]
    candidates = candidates[: args.max]

    if not candidates:
        print("Nenhum item novo pra ensinar agora (tudo ja foi avaliado antes).")
        return

    print(f"{len(candidates)} candidatos a virar licao nessa rodada.\n")

    graph = build_graph()

    for item in candidates:
        item_dict = {
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "summary": item.summary,
        }
        result = graph.invoke({"item": item_dict, "profile": profile})
        profile = result.get("profile", profile)

        if not result.get("matched_gaps"):
            print(f"(pulado, nao bate com nenhum gap): {item.title}")

    save_profile(profile, PROFILE_PATH)
    print(f"\nprofile.json atualizado em {PROFILE_PATH}")


if __name__ == "__main__":
    main()
