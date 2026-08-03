"""
Wrapper fino sobre o cliente da Anthropic. Centraliza aqui pra trocar de
modelo num lugar so, e pra Fase 3 nao espalhar detalhe de SDK pelos nos
do grafo.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from anthropic import Anthropic

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY nao configurada no .env")
        _client = Anthropic(api_key=api_key)
    return _client


def call_llm(system: str, user: str, model: Optional[str] = None, max_tokens: int = 1024) -> str:
    model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def call_llm_json(system: str, user: str, model: Optional[str] = None, max_tokens: int = 1024) -> dict:
    """Chama o LLM esperando JSON de volta. Faz parse tolerante (extrai o
    primeiro bloco {...} caso venha texto em volta, apesar da instrucao).
    """
    raw = call_llm(system, user, model=model, max_tokens=max_tokens)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"resposta do LLM nao contem JSON: {raw[:200]}")
    return json.loads(raw[start:end + 1])
