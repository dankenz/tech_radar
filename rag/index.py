"""
RAG index -- Qdrant Edge + FastEmbed, tudo embutido no processo (sem
servidor separado). Guarda uma base de conhecimento tecnica local pra
ancorar as explicacoes educativas da Fase 3.

Importante: nao indexa tudo que o radar coleta. So os itens que ja
passaram pelo filtro de relevancia da Fase 1 entram aqui -- mantem a base
pequena, focada, e alinhada com os gaps/watchlist do profile.json.

Qdrant Edge esta em beta; a API pode mudar entre versoes do pacote
qdrant-edge-py. Os nomes usados aqui seguem a doc oficial em
https://qdrant.tech/documentation/edge/ na data em que este modulo foi
escrito -- se algo nao bater, confira a versao instalada.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from fastembed import TextEmbedding
from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeVectorParams,
    Point,
    Query,
    QueryRequest,
    UpdateOperation,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARD_DIR = os.path.join(BASE_DIR, "storage", "qdrant_edge")
MODELS_DIR = os.path.join(BASE_DIR, "storage", "fastembed_models")

VECTOR_NAME = "text"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # 384 dimensoes, leve, roda bem em CPU local
VECTOR_DIM = 384


def get_embedder() -> TextEmbedding:
    Path(MODELS_DIR).mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=MODELS_DIR)


def open_shard() -> EdgeShard:
    """Abre o shard existente, ou cria um novo se ainda nao existir dado
    nenhum no diretorio de storage.
    """
    Path(SHARD_DIR).mkdir(parents=True, exist_ok=True)
    if any(Path(SHARD_DIR).iterdir()):
        return EdgeShard.load(SHARD_DIR)

    config = EdgeConfig(
        vectors={
            VECTOR_NAME: EdgeVectorParams(size=VECTOR_DIM, distance=Distance.Cosine)
        }
    )
    return EdgeShard.create(SHARD_DIR, config)


def _doc_text(title: str, summary: str) -> str:
    return f"{title}\n\n{summary}".strip()


def _stable_id(url: str) -> str:
    """ID deterministico a partir da URL -- reindexar o mesmo item so
    atualiza o ponto existente (upsert), nao duplica.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


def index_items(items: Iterable, embedder: Optional[TextEmbedding] = None) -> int:
    """Embeda e indexa uma lista de Item (de tools.rss_source.Item) no
    shard local. Retorna quantos pontos foram enviados.
    """
    items = [i for i in items if i.url]  # sem URL nao da pra gerar ID estavel
    if not items:
        return 0

    embedder = embedder or get_embedder()
    texts = [_doc_text(i.title, i.summary) for i in items]
    vectors = list(embedder.embed(texts))

    points = []
    for item, vec in zip(items, vectors):
        points.append(
            Point(
                id=_stable_id(item.url),
                vector={VECTOR_NAME: vec.tolist()},
                payload={
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    "published": item.published,
                    "summary": item.summary,
                    "tags": list(item.tags),
                },
            )
        )

    shard = open_shard()
    shard.update(UpdateOperation.upsert_points(points))
    shard.optimize()  # Edge nao tem otimizador em background, precisa chamar manual
    shard.close()
    return len(points)


def query(text: str, top_k: int = 5) -> List[dict]:
    """Busca os top_k documentos mais proximos semanticamente de `text`.
    Retorna uma lista de payloads (title, url, source, summary, ...).
    """
    if not Path(SHARD_DIR).exists() or not any(Path(SHARD_DIR).iterdir()):
        return []

    embedder = get_embedder()
    vec = list(embedder.embed([text]))[0]

    shard = EdgeShard.load(SHARD_DIR)
    results = shard.query(
        QueryRequest(
            query=Query.Nearest(vec.tolist(), using=VECTOR_NAME),
            limit=top_k,
            with_vector=False,
            with_payload=True,
        )
    )
    shard.close()

    # O shape exato do retorno pode variar por versao do qdrant-edge-py
    # (lista direta de pontos, ou um objeto com `.points`). Tenta os dois.
    points = getattr(results, "points", results)
    return [p.payload for p in points]
