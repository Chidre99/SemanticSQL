# SemanticSQL

> Natural-language-to-SQL with retrieval-augmented context, structured
> validation, and self-correction — running entirely on a local 7B model.
> Pose a question in English, get back safe, validated SQL plus the
> answer. Hallucinated table/column names are caught before they reach
> the database; failures trigger a self-correction retry with the
> structured error fed back into the prompt.

**Headline result:** on an 80-query benchmark spanning two production-style
schemas (Pagila/Postgres, Chinook/MySQL), RAG + validation + retry reduces
the rate of hallucinated identifiers from **<baseline>%** to **<treatment>%**
— a relative reduction of **<X>%**. (Numbers populated by `make eval`;
this README links to the CSV.)

> Open `eval/results/run-*.csv` for the per-query breakdown.

---

## Architecture

```
                                ┌────────────────────────┐
  natural-language question ──▶│  RAG retriever         │── ChromaDB
                                │  (embed → top-k +      │     ↑
                                │   FK-graph expansion)  │     │ index built from
                                └──────────┬─────────────┘     │ databases/metadata/*.yaml
                                           │
                                           ▼
                                ┌────────────────────────┐
                                │  Prompt builder        │
                                │  system + few-shots +  │
                                │  retrieved schema +    │
                                │  question (+ errors    │
                                │  on retry)             │
                                └──────────┬─────────────┘
                                           │
                                           ▼
                                ┌────────────────────────┐
                                │  Qwen 2.5 Coder 7B     │── Ollama (OpenAI-compat)
                                │  (streamed tokens)     │
                                └──────────┬─────────────┘
                                           │
                                           ▼
                                ┌────────────────────────┐
                                │  Validation pipeline   │
                                │  parse → policy →      │
                                │  identifiers (+ live   │
                                │  schema check) →       │
                                │  EXPLAIN dry-run       │
                                └─────┬───────────┬──────┘
                              fail   │           │  ok
                                      │           ▼
                                      │     ┌──────────────┐
                              ≤N      │     │  Execute     │── read-only Postgres / MySQL
                              retries│     │  (timeout)   │
                                      │     └──────┬───────┘
                                      └──── back into prompt with structured errors
                                            │
                                            ▼
                                       streamed rows
```

The orchestrator is a **framework-free async generator** that emits
typed events (`retrieval_start`, `sql_token`, `validation_complete`,
`row`, `done`, …). FastAPI's SSE handler and the eval runner both
consume the same generator — there's exactly one code path for the
"brain".

## Stack & rationale

| Component         | Choice                                   | Why                                                                |
|-------------------|------------------------------------------|---------------------------------------------------------------------|
| LLM               | Qwen 2.5 Coder 7B Instruct via Ollama    | Strong code/SQL tuning, runs locally on 8 GB+ RAM, zero API cost   |
| Embeddings        | `BAAI/bge-small-en-v1.5`                 | Small (~120 MB), strong at short technical text, normalized output |
| Vector store      | ChromaDB (persistent)                    | Zero infra; single import; cosine via `hnsw:space`                 |
| SQL parser        | sqlglot                                  | Multi-dialect, AST walk, structured errors                         |
| Backend           | FastAPI + AsyncOpenAI + asyncpg/aiomysql | Async end-to-end, SSE streaming, OpenAI-compatible client          |
| Frontend          | React + Vite + TS + Tailwind             | Standard, fast, clean styling                                      |
| Editor            | CodeMirror 6                             | Native SQL grammar; debounced live validation                      |
| Table             | TanStack Table                           | Sortable, virtualizable, no opinion on style                       |
| Eval              | diskcache + pandas + rich                | Cheap reruns, easy aggregation, readable CLI output                |

## Validation, in detail

Four layers, each producing a structured report; the final report is
the same object the editor renders inline and the retry loop feeds back
to the model:

| Layer        | Catches                                                          |
|--------------|------------------------------------------------------------------|
| **Parser**   | syntax errors before anything else runs                          |
| **Policy**   | multi-statement; non-SELECT (INSERT/UPDATE/DELETE/DDL); `pg_catalog` / `information_schema`; `pg_read_file`, `load_file`, etc. |
| **Identifiers** | tables and columns that don't exist in the live schema. Suggestions via `difflib.get_close_matches` |
| **Dry-run**  | `EXPLAIN` against a read-only connection with a 2s statement timeout |

Plus a final belt: the application connects as `readonly_user`. Even
if every check above failed, the DB would still refuse writes.

## Eval methodology

- **80 NL questions**, hand-authored, with verified ground-truth SQL — 40 for Pagila, 40 for Chinook.
- **Distribution per DB:** 8 simple lookups, 12 filter+order, 10 single-joins, 6 multi-join aggregates, 4 tricky (subquery / CASE / date math / self-join / NOT EXISTS).
- **Conditions:**
  - *Baseline* — minimal system prompt with just the table list. No retrieval, no few-shots, no validation feedback, no retry.
  - *Treatment* — full orchestrator (RAG retrieval, few-shots, validation pipeline, up to 2 retries with structured error feedback).
- **Metrics:**
  - `parse_rate` — does sqlglot parse it?
  - `policy_pass_rate` — survives the SELECT-only / no-system-tables checks?
  - `identifier_valid_rate` — every table/column actually exists?
  - **`hallucination_rate` = 1 − identifier_valid_rate** *(headline)*
  - `execution_rate` — does it execute (`EXPLAIN` ok)?
  - `result_match_rate` — does the result set match ground truth (sorted unless `ORDER BY`)?
- **Caching:** every LLM call goes through `diskcache` keyed on `sha256(model + condition + prompt)`. Reruns are nearly free.

Each run writes a per-query CSV to `eval/results/run-YYYYMMDD-HHMMSS.csv`,
plus a one-line failure-cause breakdown for the treatment condition.

## Quickstart

Requirements:
- **Docker** (for Postgres + MySQL)
- **Python 3.11+**
- **Node.js 20+**
- **Ollama** with `qwen2.5-coder:7b-instruct` pulled (~4.7 GB)
- **~16 GB RAM** recommended (8 GB possible)

```bash
# 1. Ollama (host)
brew install ollama        # or your platform's equivalent
ollama serve &
ollama pull qwen2.5-coder:7b-instruct

# 2. Repo
git clone <this-repo> && cd semanticsql
cp .env.example .env

# 3. Data + databases
make fetch-data            # downloads Pagila + Chinook SQL dumps
make up                    # starts Postgres + MySQL via docker compose

# 4. Backend + index
make install               # creates backend/.venv, installs deps (incl. editable eval/)
make index                 # builds ChromaDB from databases/metadata/*.yaml
make warmup                # preloads the model

# 5. Run
make serve                 # FastAPI on http://localhost:8000
make frontend              # Vite dev server on http://localhost:5173

# 6. Eval
make eval                  # baseline vs treatment, prints summary
```

`make demo` runs steps 3–5 in one command and opens the browser.

## API reference (short)

| Method | Path                           | Notes                                                                          |
|--------|--------------------------------|--------------------------------------------------------------------------------|
| POST   | `/query`                       | `{question, database}` → SSE event stream (see `frontend/src/lib/types.ts`)    |
| POST   | `/validate`                    | `{sql, database}` → structured validation report                               |
| GET    | `/schemas`                     | list of available databases                                                    |
| GET    | `/schemas/{db}`                | tables in a database                                                           |
| GET    | `/schemas/{db}/{table}`        | columns + 5 sample rows                                                        |
| POST   | `/feedback`                    | `{question, sql, was_correct, comments?}` → appended to `eval/results/feedback.jsonl` |
| GET    | `/health`                      | pings Ollama and both DBs                                                      |

## Repository layout

```
semanticsql/
├── databases/           Postgres/MySQL init scripts + hand-authored metadata YAML
├── backend/             FastAPI app, RAG, validation, orchestrator, scripts, tests
│   └── app/
│       ├── llm/         client + prompts + streaming
│       ├── rag/         embeddings, indexer, retriever
│       ├── validation/  parser, policy, identifiers, dryrun
│       ├── db/          asyncpg + aiomysql pools + introspection cache
│       ├── api/         FastAPI routers (one file per endpoint)
│       └── orchestrator.py
├── eval/                Eval harness with diskcache + pandas + rich
└── frontend/            Vite + React + TS + Tailwind + CodeMirror
```

## What I'd do differently

- **Two-stage retrieval.** Right now we embed the whole question and
  use cosine plus FK expansion. A first-pass intent classifier
  (lookup vs. aggregate vs. comparison) would let us bias retrieval —
  aggregates almost always need the FK-linked fact table.
- **Eval set growth.** 80 queries is enough to be defensible, not enough
  for confidence intervals. Doubling it and bootstrapping CIs would
  make the headline number harder to dismiss.
- **Smaller retry model.** Currently we retry with the same 7B. Cheap
  retries on a 1.5B with the structured error in-prompt would be faster
  and would isolate "did the bigger model fix it or did the feedback?"
- **Schema diffing.** The metadata YAML is hand-authored. A CI check
  that diffs it against `information_schema` would catch drift before
  it produces silent retrieval misses.
- **First-class refusals.** The model currently refuses unanswerable
  questions via a sentinel SELECT. A real refusal channel (`type: "refuse"`
  with explanation) would make the UI less confusing for those cases.

## License

MIT.
