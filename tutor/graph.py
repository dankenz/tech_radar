"""
Fase 3 -- grafo LangGraph que liga classificador de conceitos, tutor e
loop de feedback. Tres papeis, um grafo so:

  1. classify_concepts        (agente CLASSIFICADOR) -- extrai conceitos
     tecnicos do item via LLM e cruza com os gaps do profile.
  2. retrieve_context +
     generate_lesson           (agente TUTOR) -- busca contexto na base RAG
     (Fase 2) e gera uma explicacao curta e pratica ancorada nisso.
  3. collect_feedback +
     update_profile             (LOOP DE FEEDBACK) -- pergunta pro usuario
     se entendeu, e atualiza o profile em memoria (quem persiste em disco
     e o orquestrador, tutor/run_lesson.py).

Se o item nao bater com nenhum gap de conhecimento, o grafo pula direto
pro fim -- nao vale a pena gastar chamada de LLM/RAG numa noticia que nao
e oportunidade de aprendizado.

LangGraph e uma lib relativamente estavel nesse nivel de API (StateGraph,
add_node, add_edge, add_conditional_edges, compile), mas se algo nao bater
exatamente, confira a versao instalada com `pip show langgraph`.
"""
from __future__ import annotations

import datetime
from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index import query as rag_query
from tutor.llm import call_llm, call_llm_json


class LessonState(TypedDict, total=False):
    item: dict
    profile: dict
    concepts: List[str]
    matched_gaps: List[dict]
    context_snippets: List[dict]
    lesson_text: str
    feedback: Optional[str]


def classify_concepts(state: LessonState) -> LessonState:
    """Agente CLASSIFICADOR: pede pro LLM listar os conceitos tecnicos que
    o item pressupoe, e cruza com os topicos do profile.
    """
    item = state["item"]

    system = (
        "Voce extrai conceitos tecnicos de um titulo/resumo de artigo. "
        'Responda APENAS com JSON no formato {"concepts": ["conceito1", "conceito2"]}. '
        "Liste no maximo 5 conceitos, os mais especificos e relevantes."
    )
    user = f"Titulo: {item['title']}\nResumo: {item.get('summary', '')}"

    result = call_llm_json(system, user)
    concepts = [str(c).lower().strip() for c in result.get("concepts", [])]

    matched_gaps = []
    for gap in state["profile"].get("knowledge_gaps", []):
        gap_topic = gap["topic"].lower()
        if any(gap_topic in c or c in gap_topic for c in concepts):
            matched_gaps.append(gap)

    return {**state, "concepts": concepts, "matched_gaps": matched_gaps}


def _has_gaps(state: LessonState) -> str:
    return "continue" if state.get("matched_gaps") else "skip"


def retrieve_context(state: LessonState) -> LessonState:
    """Agente TUTOR (parte 1): busca trechos na base RAG local (Fase 2) pra
    ancorar a explicacao, em vez de depender so da memoria do LLM.
    """
    item = state["item"]
    snippets = rag_query(f"{item['title']} {item.get('summary', '')}", top_k=3)
    return {**state, "context_snippets": snippets}


def generate_lesson(state: LessonState) -> LessonState:
    """Agente TUTOR (parte 2): gera a explicacao curta e pratica, respeitando
    content_preferences do profile (pratico/blog por padrao, definido la na
    conversa sobre profundidade de conteudo).
    """
    item = state["item"]
    gaps = state["matched_gaps"]
    prefs = state["profile"].get("content_preferences", {})
    context = state.get("context_snippets", [])
    style = prefs.get("default_style", "pratico e aplicado")

    gap_names = ", ".join(g["topic"] for g in gaps)

    context_lines = []
    for c in context:
        title = c.get("title", "")
        summary = str(c.get("summary", ""))[:200]
        context_lines.append(f"- {title}: {summary}")
    context_text = "\n".join(context_lines) or "(nenhum contexto encontrado)"

    system = (
        "Voce e um tutor tecnico. Escreva uma explicacao curta (2-3 paragrafos), "
        f"em portugues, no estilo: {style}. "
        "Ancore a explicacao no contexto fornecido quando fizer sentido, mas nao "
        "invente fatos que nao estejam no contexto ou no item original. Foque em "
        "como o conceito aparece na pratica do dia a dia de um engenheiro."
    )
    item_summary = item.get("summary", "")
    user = (
        f"Artigo: {item['title']}\n{item_summary}\n\n"
        f"Conceitos-gap a explicar: {gap_names}\n\n"
        f"Contexto de referencia (base RAG):\n{context_text}"
    )

    lesson = call_llm(system, user, max_tokens=600)
    return {**state, "lesson_text": lesson}


def collect_feedback(state: LessonState) -> LessonState:
    """LOOP DE FEEDBACK (parte 1): pergunta pro usuario o nivel de
    entendimento. Em modo nao-interativo (sem stdin), so pula.
    """
    print("\n" + "=" * 70)
    print(f"LICAO: {state['item']['title']}")
    print("=" * 70)
    print(state["lesson_text"])

    if state.get("context_snippets"):
        print("\nFontes (base RAG):")
        for c in state["context_snippets"]:
            print(f"  - {c.get('title')} ({c.get('url')})")

    try:
        resp = input(
            "\nComo ficou seu entendimento? "
            "[1] entendi bem  [2] preciso revisar  [3] nao entendi  [enter=pular]: "
        ).strip()
    except EOFError:
        resp = ""

    feedback_map = {"1": "entendi_bem", "2": "preciso_revisar", "3": "nao_entendi"}
    return {**state, "feedback": feedback_map.get(resp)}


DEFAULT_LEVEL_SCALE = {
    "0": "nenhum conhecimento",
    "1": "ja ouviu falar / entende o conceito em teoria, nunca usou na pratica",
    "2": "usa na pratica com apoio (tutorial, copiar-colar), nao entende nuances",
    "3": "usa com confianca no dia a dia, entende conceitos principais e casos de uso comuns",
    "4": "entende trade-offs e nuances, consegue tomar decisoes de arquitetura",
    "5": "especialista -- acompanha estado da arte, consegue ensinar outros",
}


def _refresh_notes(gap: dict, feedback: str, concepts: List[str], level_scale: dict) -> str:
    """Pede pro LLM reescrever a nota de autoavaliacao em 1 frase curta,
    coerente com o nivel novo -- sem isso a nota fica presa no texto
    original (ex: "nenhum conhecimento" com o nivel ja em 3).
    """
    new_level = str(gap.get("level", 0))
    system = (
        "Voce atualiza a nota de autoavaliacao de conhecimento de um profissional "
        "sobre um topico tecnico. Escreva 1 frase curta e factual, em portugues, "
        "resumindo o nivel real de entendimento apos a licao. Nao exagere o nivel -- "
        "ler um artigo curto nao vira dominio pratico. Responda so com a frase, sem aspas."
    )
    user = (
        f"Topico: {gap['topic']}\n"
        f"Nota anterior: {gap.get('notes', '')}\n"
        f"Nivel novo: {new_level}/5 -- {level_scale.get(new_level, '')}\n"
        f"Conceitos cobertos nessa licao: {', '.join(concepts)}\n"
        f"Feedback do usuario: {feedback}"
    )
    try:
        return call_llm(system, user, max_tokens=120).strip()
    except Exception:
        return gap.get("notes", "")  # se o LLM falhar, mantem a nota antiga em vez de quebrar


def update_profile(state: LessonState) -> LessonState:
    """LOOP DE FEEDBACK (parte 2): ajusta o nivel dos gaps atingidos e
    registra no feedback_log. So mexe no dict em memoria -- quem persiste
    em disco e o orquestrador (tutor/run_lesson.py).

    Importante: cada topico so pode subir de nivel (e ter a nota reescrita)
    UMA VEZ por dia. Sem esse limite, varias licoes da mesma rodada que
    batem no mesmo gap (mesmo que fracamente relacionadas) empilham nivel
    demais de uma vez so -- ver a régua em DEFAULT_LEVEL_SCALE.
    """
    feedback = state.get("feedback")
    if not feedback:
        return state

    today = datetime.date.today().isoformat()
    profile = state["profile"]
    level_scale = profile.get("level_scale", DEFAULT_LEVEL_SCALE)
    concepts = state.get("concepts", [])

    for gap in profile.get("knowledge_gaps", []):
        if gap not in state["matched_gaps"]:
            continue

        already_bumped_today = gap.get("last_reviewed") == today
        if already_bumped_today:
            continue  # outro item da mesma rodada/dia ja atualizou esse gap

        if feedback == "entendi_bem":
            gap["level"] = min(5, gap.get("level", 0) + 1)
        gap["last_reviewed"] = today
        gap["notes"] = _refresh_notes(gap, feedback, concepts, level_scale)

    profile.setdefault("feedback_log", []).append(
        {
            "date": today,
            "item_title": state["item"]["title"],
            "item_url": state["item"]["url"],
            "concepts": concepts,
            "feedback": feedback,
        }
    )

    return {**state, "profile": profile}


def build_graph():
    """Grafo completo (usado por tutor/run_lesson.py, modo terminal): pede
    feedback com input() e ja atualiza o profile no mesmo processo.
    """
    graph = StateGraph(LessonState)
    graph.add_node("classify_concepts", classify_concepts)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_lesson", generate_lesson)
    graph.add_node("collect_feedback", collect_feedback)
    graph.add_node("update_profile", update_profile)

    graph.add_edge(START, "classify_concepts")
    graph.add_conditional_edges(
        "classify_concepts",
        _has_gaps,
        {"continue": "retrieve_context", "skip": END},
    )
    graph.add_edge("retrieve_context", "generate_lesson")
    graph.add_edge("generate_lesson", "collect_feedback")
    graph.add_edge("collect_feedback", "update_profile")
    graph.add_edge("update_profile", END)

    return graph.compile()


def build_send_graph():
    """Grafo parcial (usado por tutor/run_bot.py, modo Telegram): para em
    generate_lesson, sem pedir feedback com input(). O bot manda a licao e
    guarda o item pendente (tutor/pending.py); o feedback chega numa
    execucao futura, via mensagem no Telegram, e e aplicado direto com
    update_profile() -- chamado como funcao pura, fora do grafo.
    """
    graph = StateGraph(LessonState)
    graph.add_node("classify_concepts", classify_concepts)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_lesson", generate_lesson)

    graph.add_edge(START, "classify_concepts")
    graph.add_conditional_edges(
        "classify_concepts",
        _has_gaps,
        {"continue": "retrieve_context", "skip": END},
    )
    graph.add_edge("retrieve_context", "generate_lesson")
    graph.add_edge("generate_lesson", END)

    return graph.compile()
