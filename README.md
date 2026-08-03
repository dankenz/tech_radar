# Radar

Agente de curadoria tecnica + base de conhecimento pessoal (RAG), construido
em fases.

## Fase 1 -- Agente curador (tool use)

Busca em RSS, Hacker News, dev.to e GNews/NewsAPI, filtra contra
`config/profile.json` (seus gaps de conhecimento + watchlist estrategica).

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# preencha GNEWS_API_KEY e NEWSAPI_KEY no .env
```

### Rodar

```bash
python main.py
```

Imprime quantos itens cada fonte contribuiu e um digest ranqueado por
relevancia. RSS, HN e dev.to funcionam sem chave.

## Fase 2 -- Base RAG local (Qdrant Edge + FastEmbed)

Guarda os itens relevantes coletados pela Fase 1 numa base vetorial local
(Qdrant Edge, embutido no processo, sem servidor separado), pra ancorar
explicacoes educativas na Fase 3 em vez de depender so da memoria do LLM.

Embeddings sao gerados localmente via FastEmbed (`BAAI/bge-small-en-v1.5`,
384 dimensoes) -- primeira execucao baixa o modelo (~130MB) e fica em cache
em `storage/fastembed_models/`. Depois disso roda offline.

### Popular a base

```bash
python -m rag.build_index
```

Roda o mesmo pipeline de busca+filtro da Fase 1 e indexa os itens
relevantes. Rode de novo sempre que quiser atualizar a base com conteudo
mais recente -- reindexar a mesma URL so atualiza o ponto existente, nao
duplica.

### Testar a busca

```bash
python -m rag.query_index "kubernetes autoscaling"
```

Retorna os 5 itens semanticamente mais proximos da sua pergunta, com
titulo, fonte e link.

### Onde fica salvo

```
storage/
  qdrant_edge/        # o shard local -- seus dados de verdade
  fastembed_models/    # cache do modelo de embedding baixado
```

Nota: o Qdrant Edge pre-aloca 32MB de WAL por shard, entao a pasta pode
mostrar ~32MB mesmo com poucos dados -- isso e espaco reservado, nao uso
real (mais detalhes na nossa conversa sobre dimensionamento).

Qdrant Edge esta em beta -- se algum metodo/parametro do pacote
`qdrant-edge-py` nao bater exatamente com o que esta em `rag/index.py`,
provavelmente a API mudou de versao; confira a doc oficial em
qdrant.tech/documentation/edge/.

## Estrutura

```
config/
  profile.json         # perfil de conhecimento + watchlist estrategica
  rss_sources.yaml      # blogs de engenharia curados, tagueados por topico
tools/
  rss_source.py          # feedparser sobre rss_sources.yaml
  hn_source.py             # Hacker News via Algolia API (sem chave)
  devto_source.py           # dev.to API (sem chave)
  news_source.py              # GNews + NewsAPI (precisa de chave)
relevance.py                  # scoring heuristico -- vira classificador via LLM na Fase 3
main.py                        # orquestra a Fase 1 e imprime o digest
rag/
  index.py                       # wrapper do Qdrant Edge + FastEmbed
  build_index.py                   # popula a base a partir do pipeline da Fase 1
  query_index.py                    # teste manual de busca
storage/                             # dados locais (Qdrant Edge + cache de modelos)
tutor/
  llm.py                          # wrapper do cliente Anthropic
  graph.py                         # grafo LangGraph: classificador + tutor + feedback
  run_lesson.py                     # ponto de entrada da Fase 3 (terminal)
  telegram_bot.py                    # cliente minimo da API do Telegram
  pending.py                          # estado de licoes aguardando feedback
  run_bot.py                           # ponto de entrada da Fase 4 (Telegram, agendado)
```

## Fase 3 -- Classificador + tutor + loop de feedback (multi-agente)

Um grafo LangGraph com tres papeis:

1. **Classificador** -- pede pro LLM (Anthropic) extrair os conceitos
   tecnicos de cada item e cruza com `knowledge_gaps` do profile.
2. **Tutor** -- se bateu com algum gap, busca contexto na base RAG (Fase 2)
   e gera uma explicacao curta e pratica ancorada nisso.
3. **Loop de feedback** -- pergunta seu nivel de entendimento e atualiza
   `profile.json` (nivel do gap, `last_reviewed`, `feedback_log`).

Itens sem gap batido pulam direto pro fim (sem gastar LLM/RAG a toa).

### Setup extra

```bash
# preencha no .env:
ANTHROPIC_API_KEY=...
# opcional, padrao e claude-sonnet-5:
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

### Rodar

```bash
python -m tutor.run_lesson          # ate 3 licoes por rodada
python -m tutor.run_lesson --max 5  # ajusta quantas
```

Cada item ja avaliado uma vez (registrado em `feedback_log`) nao repete em
rodadas futuras. `profile.json` e reescrito no final com os niveis e o log
atualizados.

### Sobre o multi-agente

Os tres papeis rodam como nos de um `StateGraph` do LangGraph, nao como
processos separados -- pra um projeto pessoal isso e suficiente e mais
simples de debugar que multi-processo de verdade. `tutor/graph.py` tem o
grafo comentado no-a-no se quiser entender o fluxo.

## Fase 4 -- Bot de Telegram + agendamento

Em vez de rodar `tutor.run_lesson` no terminal, o bot manda as licoes por
Telegram e recebe seu feedback (1/2/3) por mensagem, numa execucao
agendada (ex: 2x por semana). Sem servidor rodando o tempo todo -- cada
execucao agendada primeiro processa feedback pendente, depois manda
licoes novas.

### Setup do bot

1. No Telegram, fale com **@BotFather**, mande `/newbot`, siga as
   instrucoes e copie o token gerado.
2. Cole o token em `TELEGRAM_BOT_TOKEN` no `.env`.
3. Mande qualquer mensagem pro seu bot no Telegram (ele nao pode iniciar
   a conversa).
4. Rode:
   ```bash
   python -m tutor.telegram_bot
   ```
   Isso imprime seu `chat_id` -- cole em `TELEGRAM_CHAT_ID` no `.env`.

### Rodar manualmente (teste)

```bash
python -m tutor.run_bot          # ate 2 licoes novas
python -m tutor.run_bot --max 1  # ajusta quantas
```

### Agendar 2x por semana (Windows Task Scheduler)

Via linha de comando (ajuste os caminhos pro seu ambiente):

```powershell
schtasks /create /tn "Radar - Aulas" ^
  /tr "C:\Users\dkenz\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\local-agent-mode-sessions\23040a5a-d223-4087-a4ea-6f0e3693fdd7\bf72b76b-e68d-40a8-b36c-bdb188d5ee6f\local_dcef25be-7296-41ab-a43b-afbd731a42dd\outputs\radar\tutor\run_bot.py" ^
  /sc weekly /d MON,THU /st 09:00 ^
  /rl LIMITED
```

Use o `python.exe` de dentro do seu ambiente virtual (onde instalou o
`requirements.txt`), e configure o "Start in" (diretorio inicial) pra
pasta do projeto -- ou rode via um `.bat` que faz `cd` pra pasta antes.
Alternativa: `taskschd.msc` (interface grafica) pra criar a mesma tarefa
visualmente.

### Como o feedback e casado com a licao certa

Como nao ha processo esperando sua resposta em tempo real, cada licao
enviada fica registrada em `storage/pending_feedback.json` ate voce
responder. Na proxima execucao agendada, cada resposta numerica (1/2/3)
que chegou e aplicada a licao pendente mais antiga (FIFO) -- ou seja,
responda na mesma ordem em que as licoes chegaram. Pra 2 licoes por
rodada isso costuma ser trivial na pratica.

## Proximos passos

Documentar a arquitetura completa e preparar o case pra portfolio (README
mais robusto, screenshots/exemplos reais de licao gerada, incluindo o bot).
