"""
Fase 2 -- teste manual de busca na base RAG.

Uso:
    python -m rag.query_index "kubernetes autoscaling"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.index import query  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print('Uso: python -m rag.query_index "sua pergunta ou topico"')
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    results = query(text, top_k=5)

    if not results:
        print("Nenhum resultado (base RAG vazia? rode build_index.py primeiro).")
        return

    print(f"Top {len(results)} resultados para: {text}\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.get('title')}")
        print(f"   fonte: {r.get('source')}")
        print(f"   {r.get('url')}")
        print()


if __name__ == "__main__":
    main()
