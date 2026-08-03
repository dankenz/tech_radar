"""
Guarda o estado de licoes enviadas pelo bot que ainda esperam feedback.

Sem isso, quando voce responde "1"/"2"/"3" no Telegram numa execucao
futura do agendador, nao haveria como saber a qual licao a resposta se
refere -- o processo que gerou a licao ja terminou faz tempo.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_PATH = os.path.join(BASE_DIR, "storage", "pending_feedback.json")


def load_pending() -> List[dict]:
    if not os.path.exists(PENDING_PATH):
        return []
    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending(pending: List[dict]) -> None:
    Path(os.path.dirname(PENDING_PATH)).mkdir(parents=True, exist_ok=True)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def pop_oldest() -> Optional[dict]:
    pending = load_pending()
    if not pending:
        return None
    entry = pending.pop(0)
    save_pending(pending)
    return entry
