"""
Filtro de relevância — cruza itens coletados com config/profile.json.

Nesta Fase 1 o critério é heurístico (match de palavra-chave/tag), sem LLM:
o objetivo é ter um digest útil rodando rápido. A classificação semântica
de conceitos (o que realmente liga uma notícia a um gap de conhecimento)
fica pra Fase 3, quando entra o agente classificador.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List

from tools.rss_source import Item


@dataclass
class ScoredItem:
    item: Item
    score: float
    reasons: List[str]


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9À-ÿ\s]", " ", text.lower())


_STOPWORDS = {
    "de", "da", "do", "das", "dos", "com", "em", "para", "sem", "mas", "nada",
    "nenhum", "the", "and", "for", "with", "of", "a", "o", "e", "um", "uma",
}


def _topic_keywords(topic: str) -> List[str]:
    """Quebra um topico/tema composto em keywords que tem chance real de
    aparecer literalmente num titulo/resumo curto.

    Dois niveis: a frase inteira de cada parte separada por "," ou "/" (bom
    pra topicos curtos e especificos, tipo "AWS, GCP, Azure" -> "aws"), e
    tambem as palavras individuais >4 letras dentro de cada parte (bom pra
    temas longos da watchlist, tipo "automacao de trabalho freelance com ia"
    -> "automacao", "trabalho", "freelance" -- exigir a frase inteira quase
    nunca bate num artigo real).
    """
    parts = re.split(r"[,/]", topic.lower())
    keywords: List[str] = []
    for part in parts:
        cleaned = _normalize(part).strip()
        if not cleaned:
            continue
        if cleaned not in _STOPWORDS:
            keywords.append(cleaned)
        # so quebra em palavras individuais quando a parte e uma frase longa
        # (temas da watchlist, tipo "automacao de trabalho freelance com ia").
        # Topicos curtos de 2-3 palavras (ex: "Distributed Training", "Model
        # Serving") ficam so com a frase inteira, senao uma palavra generica
        # como "training" ou "serving" sozinha passa a bater em quase tudo.
        words = cleaned.split()
        if len(words) >= 4:
            for word in words:
                if len(word) > 4 and word not in _STOPWORDS and word not in keywords:
                    keywords.append(word)
    return keywords


def _keyword_in_text(keyword: str, haystack: str) -> bool:
    """Match por palavra/frase inteira (word boundary), evita falso positivo
    tipo "rag" casando dentro de "storage".
    """
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, haystack) is not None


def score_item(item: Item, profile: dict) -> ScoredItem:
    """Pontua um item combinando dois sinais, com pesos bem diferentes:

    - match de CONTEUDO (palavra-chave do topico aparece no titulo/resumo do
      item) - sinal forte, e sobre isso que o item especifico fala.
    - match de TAG da fonte (a fonte cobre esse assunto em geral) - sinal
      fraco, e so um prior de "essa fonte e relevante pro tema", nao prova
      que este item especifico seja sobre o tema. Serve de bonus pequeno,
      nao deve carregar o score sozinho.
    """
    haystack = _normalize(f"{item.title} {item.summary}")
    source_tags = {t.lower() for t in item.tags}
    score = 0.0
    reasons: List[str] = []

    for gap in profile.get("knowledge_gaps", []):
        topic = gap["topic"]
        keywords = _topic_keywords(topic)
        content_hit = any(_keyword_in_text(k, haystack) for k in keywords)
        tag_hit = topic.lower() in source_tags

        if content_hit:
            gap_weight = max(1, 5 - gap.get("level", 0))
            score += gap_weight
            reasons.append(f"gap de conhecimento (conteudo): {topic} (nivel {gap.get('level', 0)})")
        elif tag_hit:
            score += 0.5
            reasons.append(f"gap de conhecimento (fonte relacionada): {topic}")

    for watch in profile.get("strategic_watchlist", []):
        theme = watch["theme"]
        keywords = _topic_keywords(theme)
        if any(_keyword_in_text(k, haystack) for k in keywords if len(k) > 3):
            priority_weight = {"alta": 3, "média": 2, "baixa": 1}.get(watch.get("priority", "média"), 2)
            score += priority_weight
            reasons.append(f"watchlist: {theme} (prioridade {watch.get('priority')})")

    return ScoredItem(item=item, score=score, reasons=reasons)


def rank_items(items: List[Item], profile: dict, min_score: float = 1.0) -> List[ScoredItem]:
    scored = [score_item(i, profile) for i in items]
    scored = [s for s in scored if s.score >= min_score]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def diversify(scored: List[ScoredItem], max_per_source: int = 3) -> List[ScoredItem]:
    """Limita quantos itens da mesma fonte aparecem no digest final.

    Sem isso, uma fonte muito ativa e muito alinhada a um gap grande (ex: o
    blog oficial do Kubernetes, quando kubernetes tem nivel 0) sozinha lota
    o topo do ranking e esconde itens de outras fontes/topicos igualmente
    relevantes. `scored` ja deve vir ordenado por score decrescente.
    """
    count_per_source = {}
    diversified = []
    for s in scored:
        c = count_per_source.get(s.item.source, 0)
        if c < max_per_source:
            diversified.append(s)
            count_per_source[s.item.source] = c + 1
    return diversified


def dedupe(items: List[Item]) -> List[Item]:
    seen_urls = set()
    unique = []
    for i in items:
        if i.url and i.url not in seen_urls:
            seen_urls.add(i.url)
            unique.append(i)
    return unique
