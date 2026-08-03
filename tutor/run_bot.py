"""
Fase 4 -- ponto de entrada do bot de Telegram. Pensado pra rodar via
Task Scheduler do Windows, sem interacao manual.

Cada execucao faz, nessa ordem:
  1. Processa feedback pendente -- le mensagens novas do Telegram, casa
     cada resposta numerica (1/2/3) com a licao mais antiga ainda sem
     feedback (FIFO), atualiza o profile.json.
  2. Gera e envia licoes novas (ate --max), registrando cada uma como
     pendente de feedback pra proxima execucao.

Uso:
    python -m tutor.run_bot
    python -m tutor.run_bot --max 2
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
from tutor.graph import build_send_graph, update_profile  # noqa: E402
from tutor.pending import load_pending, save_pending  # noqa: E402
from tutor.telegram_bot import get_updates, send_message  # noqa: E402

FEEDBACK_MAP = {"1": "entendi_bem", "2": "preciso_revisar", "3": "nao_entendi"}
OFFSET_PATH = Path(__file__).resolve().parent.parent / "storage" / "telegram_offset.txt"


def save_profile(profile: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def process_incoming_feedback(profile: dict) -> dict:
    """Le mensagens novas do Telegram e aplica no profile via update_profile
    (a mesma funcao usada no fluxo de terminal -- so que chamada direto,
    fora do grafo, ja que aqui nao ha um graph.invoke() esperando resposta).
    """
    pending = load_pending()
    if not pending:
        return profile

    last_offset = int(OFFSET_PATH.read_text()) if OFFSET_PATH.exists() else None
    updates = get_updates(offset=last_offset)
    if not updates:
        return profile

    for update in updates:
        last_offset = update["update_id"] + 1
        text = (update.get("message", {}) or {}).get("text", "").strip()
        feedback = FEEDBACK_MAP.get(text)
        if not feedback or not pending:
            continue

        entry = pending.pop(0)
        state = {
            "item": entry["item"],
            "profile": profile,
            "concepts": entry.get("concepts", []),
            "matched_gaps": [
                g for g in profile.get("knowledge_gaps", [])
                if g["topic"] in entry.get("matched_gap_topics", [])
            ],
            "feedback": feedback,
        }
        result = update_profile(state)
        profile = result["profile"]

    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(str(last_offset))
    save_pending(pending)
    return profile


def send_new_lessons(profile: dict, max_items: int) -> None:
    print("Coletando itens (pipeline da Fase 1)...")
    all_items = collect_all()
    ranked = rank_items(all_items, profile, min_score=1.5)

    already = {e["item"]["url"] for e in load_pending()}
    already |= {e.get("item_url") for e in profile.get("feedback_log", [])}

    candidates = [s.item for s in ranked if s.item.url not in already][:max_items]
    if not candidates:
        print("Nenhum item novo pra enviar.")
        return

    graph = build_send_graph()
    pending = load_pending()

    for item in candidates:
        item_dict = {
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "summary": item.summary,
        }
        result = graph.invoke({"item": item_dict, "profile": profile})

        if not result.get("matched_gaps"):
            continue  # nao bateu com nenhum gap, nao vale virar licao

        lesson_text = result["lesson_text"]
        sources = result.get("context_snippets", [])
        source_lines = "\n".join(f"- {s.get('title')}" for s in sources)

        message = (
            f"Aula: {item.title}\n\n{lesson_text}\n\n"
            f"Fontes:\n{source_lines}\n\n"
            "Como ficou seu entendimento? Responda 1 (entendi bem), "
            "2 (preciso revisar) ou 3 (nao entendi)."
        )
        send_message(message)
        print(f"Enviado: {item.title}")

        pending.append({
            "item": item_dict,
            "concepts": result.get("concepts", []),
            "matched_gap_topics": [g["topic"] for g in result["matched_gaps"]],
        })

    save_pending(pending)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=2, help="quantas licoes novas enviar nessa rodada")
    args = parser.parse_args()

    load_dotenv()
    profile = load_profile(PROFILE_PATH)

    profile = process_incoming_feedback(profile)
    save_profile(profile, PROFILE_PATH)

    send_new_lessons(profile, args.max)

    print("Rodada do bot concluida.")


if __name__ == "__main__":
    main()
