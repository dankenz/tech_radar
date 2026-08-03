"""
Cliente minimo pra API do Telegram Bot -- so o que a Fase 4 precisa: mandar
mensagem e ler respostas via polling. Sem SDK externo, so `requests` (que
o projeto ja usa).

Setup do bot (uma vez so):
  1. No Telegram, fale com @BotFather, mande /newbot, siga as instrucoes.
  2. Copie o token que ele te der pro .env (TELEGRAM_BOT_TOKEN).
  3. Mande QUALQUER mensagem pro seu bot no Telegram (ele nao pode iniciar
     a conversa, voce que inicia).
  4. Rode `python -m tutor.telegram_bot` uma vez -- ele imprime seu
     chat_id, que voce cola no .env (TELEGRAM_CHAT_ID).
"""
from __future__ import annotations

import os
from typing import List, Optional

import requests

BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def _url(method: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN nao configurado no .env")
    return BASE_URL.format(token=token, method=method)


def send_message(text: str, chat_id: Optional[str] = None) -> dict:
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID nao configurado no .env")

    text = text[:4000]  # Telegram limita ~4096 caracteres por mensagem

    resp = requests.post(
        _url("sendMessage"),
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def get_updates(offset: Optional[int] = None) -> List[dict]:
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset

    resp = requests.get(_url("getUpdates"), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", [])


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    updates = get_updates()
    if not updates:
        print("Nenhuma mensagem encontrada. Manda uma mensagem pro seu bot no Telegram primeiro.")
    else:
        for u in updates:
            msg = u.get("message", {})
            chat = msg.get("chat", {})
            nome = chat.get("first_name") or chat.get("username") or "?"
            print(f"chat_id: {chat.get('id')}  |  de: {nome}  |  texto: {msg.get('text')}")
