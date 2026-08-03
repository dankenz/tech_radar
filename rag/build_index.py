"""
Fase 2 -- popula a base RAG local com os itens relevantes coletados pelo
agente curador da Fase 1.

Reaproveita o pipeline inteiro do main.py (busca + filtro de relevancia) e
so manda pro indice os itens que passaram no corte -- ou seja, a base RAG
cresce organicamente a cada vez que voce roda o radar, sempre alinhada ao
profile.json atual.

Uso:
    python -m rag.build_index

"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from main import PROFILE_PATH, collect_all  # noqa: E402
from rag.index import index_items  # noqa: E402
from relevance import diversify, load_profile, rank_items  # noqa: E402


def main():
    load_dotenv()  # sem isso, GNEWS_API_KEY/NEWSAPI_KEY nao sao lidas do .env
    profile = load_profile(PROFILE_PATH)

    print("Coletando itens (mesmo pipeline da Fase 1)...")
    all_items = collect_all()
    print(f"{len(all_items)} itens unicos coletados.")

    ranked = rank_items(all_items, profile, min_score=1.5)
    print(f"{len(ranked)} itens relevantes.")

    # sem cap por fonte aqui -- pra RAG, mais cobertura e melhor que
    # diversidade no topo (isso importa pro digest, nao pro indice)
    to_index = [s.item for s in ranked]

    print(f"Gerando embeddings e indexando {len(to_index)} itens no Qdrant Edge...")
    n = index_items(to_index)
    print(f"{n} pontos indexados/atualizados na base RAG.")


if __name__ == "__main__":
    main()
