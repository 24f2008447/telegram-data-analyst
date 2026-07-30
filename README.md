# Telegram Data Analyst Bot

An LLM-powered Telegram bot that answers data-analysis questions — including
questions that reference public datasets (MOSPI and similar) — and replies
with a single JSON object, as specified by each incoming question.

## Architecture

```
Telegram message
      │
      ▼
FastAPI webhook  (app/main.py, app/webhook.py)
      │
      ▼
Conversation memory (app/agent/conversation.py)
  – tracks per-chat history for multi-turn questions
  – only triggers a reply once a message contains the "reply with
    this JSON" instruction (i.e. the actual, final question)
      │
      ▼
Planner (app/agent/planner.py)
  – LLM reads the whole conversation and decides:
    inline data vs. external dataset, dataset hint/URL,
    the operation needed, and the exact JSON output shape requested
      │
      ▼
Executor (app/agent/executor.py)
  – loads data: inline text parsing (app/analysis/parser.py) OR
    download + parse (app/analysis/downloader.py) for CSV/Excel/JSON/
    ZIP/HTML-table sources
  – dataset discovery is layered, so one wrong LLM guess doesn't sink the
    answer: try the planner's URL first; if that fails (or none was given),
    fall back to a free web search (app/analysis/websearch.py, no API key)
    and try ranked candidate links until one downloads and parses
  – supports multi-dataset joins: if the plan gives multiple dataset URLs,
    each is loaded as its own DuckDB table (data_1, data_2, ...) for the
    query to join across
  – LLM writes a DuckDB SQL query against the loaded table(s)
    (app/analysis/sql_engine.py); the query actually executes so the
    computed number/string is real, not LLM arithmetic guesswork
  – one automatic retry if the generated SQL errors out
      │
      ▼
Formatter (app/agent/formatter.py)
  – packages the computed raw result into the exact JSON shape the
    question asked for
      │
      ▼
JSONL run logger (app/logger/jsonl_logger.py)
  – every step above is appended as one JSON line to logs/run_<id>.jsonl
      │
      ▼
Log uploader (app/logger/uploader.py)
  – pushes the finished run log to a public GitHub repo via the
    Contents API, returns a public raw.githubusercontent.com URL
      │
      ▼
Reply: {"answer": ..., "log_url": "https://..."}
```

## Why this design

- **Real code computes the answer, the LLM only plans/formats.** Numbers come
  from pandas/DuckDB executing against the actual data, not from the model
  "doing math" in its head — this avoids the most common source of wrong
  answers on data tasks.
- **SQL as the universal operation language.** Instead of hand-coding every
  possible operation (mean, groupby, join, pivot, ranking, ...), the LLM
  writes one DuckDB SQL SELECT statement, which is easy to sandbox (read-only,
  single statement) and covers nearly any tabular question.
- **Multi-turn is handled by a simple, explicit trigger.** The grader's
  questions always spell out the exact JSON reply shape in the message that
  should actually be answered; earlier messages are just accumulated as
  context. Detecting that pattern is more reliable than guessing turn counts.

## Project structure

```
telegram-data-analyst/
├── app/
│   ├── main.py            # FastAPI app + webhook route + optional auto webhook registration
│   ├── config.py          # settings, all from environment variables
│   ├── webhook.py         # orchestrates the full per-message pipeline
│   ├── agent/
│   │   ├── planner.py      # LLM: decide data source / operation / output shape
│   │   ├── executor.py     # load data, LLM writes SQL, DuckDB executes it
│   │   ├── formatter.py    # LLM: package raw result into requested JSON shape
│   │   ├── conversation.py # per-chat_id history + "is this the final question" detector
│   │   └── prompts.py      # all system prompts, kept in one place
│   ├── analysis/
│   │   ├── downloader.py    # fetch CSV/Excel/JSON/ZIP/HTML from a URL
│   │   ├── parser.py        # turn a file or inline chat text into a DataFrame
│   │   ├── dataframe_engine.py  # pandas helpers: mean/median/groupby/rank/...
│   │   └── sql_engine.py    # DuckDB query runner (single + multi-table)
│   ├── logger/
│   │   ├── jsonl_logger.py  # per-run JSONL writer
│   │   └── uploader.py      # publishes the log to a public GitHub repo
│   └── utils/
│       └── llm_client.py    # thin OpenAI-compatible chat completion wrapper
├── tests/                  # pytest suite, LLM calls mocked so it runs with no API key
├── logs/                   # local copies of run logs
├── requirements.txt
├── Dockerfile
├── .env.example
└── .github/workflows/ci.yml
```

## Setup

1. **Create the Telegram bot**: message `@BotFather` on Telegram, `/newbot`,
   pick a name ending in `bot`, copy the token it gives you.
2. **Copy `.env.example` to `.env`** and fill in:
   - `TELEGRAM_BOT_TOKEN` — from BotFather
   - `TELEGRAM_WEBHOOK_SECRET` — any random string, used as part of the
     webhook path so randoms can't POST fake updates to it
   - `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` — your LLM provider
   - `GITHUB_TOKEN`, `GITHUB_LOG_REPO` — a personal access token with repo
     write access, and a public repo (e.g. `yourname/telegram-bot-logs`) to
     push run logs to
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Run locally**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Use a tunnel (e.g. `ngrok http 8000`) to get a public HTTPS URL for local
   webhook testing, and register it with Telegram:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-ngrok-url>/webhook/<TELEGRAM_WEBHOOK_SECRET>"
   ```

## Deployment (Render / Cloud Run)

1. Push this repo to GitHub (public).
2. Create a new **Web Service** on Render (or a Cloud Run service), pointing
   at the repo, using the included `Dockerfile`.
3. Set all variables from `.env.example` as environment variables in the
   host's dashboard, plus `PUBLIC_URL` set to the service's public HTTPS URL
   — the app will then auto-register its Telegram webhook on startup.
4. Confirm it's live: `GET https://<your-service>/` should return
   `{"status": "ok"}`.

## Logging

Every processed question produces `logs/run_<id>.jsonl` locally, with one
line per pipeline step (`received_message`, `planning_done`,
`execution_done`, `formatting_done`, `log_published`, or `error`). On success,
the file is pushed to the configured public GitHub repo and its raw URL is
returned as `log_url` in the reply.

## Testing

```bash
pytest tests/ -v
```

The test suite mocks all LLM calls and the log uploader, so it runs without
any API keys — it covers:
- pandas/DuckDB analysis primitives directly
- inline CSV / markdown table extraction from chat text
- per-chat conversation memory and multi-turn context building
- the full webhook pipeline end-to-end with the LLM/upload boundary mocked

For live end-to-end testing against the official grading harness, clone
[tds-p1-t2-2026-telegram-bot](https://github.com/Jivraj-18/tds-p1-t2-2026-telegram-bot),
point it at your deployed bot, and add your own questions to
`evals/questions.json`.

## Aligning with the official grading pipeline

The course's grading pipeline (`generate.py` → `collect.py` → `grade.py`) sends
each question as one or more Telegram messages (a list = a multi-turn
exchange), waits up to that question's `timeout_seconds`, and grades your
bot's final reply by **exact match** against a pre-computed answer key. A few
things in this repo exist specifically because of that:

- **Fast webhook ack, background processing** (`app/main.py`): the webhook
  handler returns to Telegram immediately and does the actual planning /
  downloading / LLM work in a background task. If a question's answer takes
  20-60s to compute, we don't want a slow HTTP request timeout on our own
  hosting platform to make the bot look unreachable before the question's
  real timeout budget is used.
  > **Cloud Run caveat**: Cloud Run freezes a container's CPU after it
  > finishes responding to a request, by default, which would kill this
  > background task before it can send the reply. If deploying there, enable
  > "CPU is always allocated" for the service, or use Render/a normal
  > always-on VM instead.
- **Multi-turn detection isn't hardcoded to one key name**
  (`app/agent/conversation.py`): different questions use different answer
  keys (`"answer"`, `"values"`, etc.), so the "is this the final message"
  check looks for the near-universal *"reply with only ..."* instruction
  rather than one specific JSON key.
- **Exact-match-aware formatting** (`app/agent/prompts.py`): the formatter is
  explicitly told to match JSON types precisely (numbers vs numeric strings),
  apply stated rounding literally, preserve key names and list order, and
  not add units/symbols the template didn't ask for - since grading compares
  values exactly, not "close enough."
- **Bounded retry budgets** (`app/utils/llm_client.py`,
  `app/analysis/downloader.py`): LLM calls and downloads use short timeouts
  and at most one retry each, so a single flaky call can't quietly eat an
  entire question's timeout budget across the planner → SQL-writer →
  formatter chain plus dataset-download attempts.

## Checklist to maximize grading marks

- [ ] **Repo is public** and this README is up to date (graders read it).
- [ ] **Bot is deployed and reachable** — check `GET /` returns `{"status": "ok"}`
      right before submitting, and again a few minutes before the grading
      window if you know it.
- [ ] **Send yourself a few real Telegram messages** in the exact format from
      the assignment's worked example and confirm the reply is *only* the raw
      JSON text — no "Here's your answer:", no ```` ```json ```` fences.
- [ ] **`log_url` actually resolves** — `wget` it yourself after a test run
      and confirm it returns valid JSONL, not a 404 or a private-repo error
      page.
- [ ] **Test multi-turn**: send 2-3 separate messages to your bot in the same
      chat, with only the last one containing the `{"answer": ...}` template,
      and confirm you get exactly one reply, after the last message.
- [ ] **Test at least one real external-dataset question** (not just inline
      data) end-to-end, since that's the harder path and most likely place to
      lose marks.
- [ ] **Test an intentionally bad/ambiguous question** and confirm the bot
      still replies with valid two-key JSON (`answer: null` is fine) instead
      of crashing or timing out silently — a non-reply scores worse than a
      wrong-but-present answer.
- [ ] **`GITHUB_TOKEN` scope**: make sure the token used for log uploads has
      write access to the log repo, and that the log repo itself is public
      (private repos won't be `wget`-able).
- [ ] **Test with the official pipeline's fake bot first** — run
      `python3 test_bot/fake_student_bot.py` from the grading pipeline repo,
      point a one-row roster at it, and run your own `evals/questions.json`
      variations through `generate.py` → `collect.py` → `grade.py` before
      relying on manual Telegram testing alone; it exercises the exact
      multi-turn / timeout / exact-match behavior you'll be graded on.
- [ ] Register your GitHub repo URL and bot username (ending in `bot`) in the
      assignment's submission field to collect the automatic 0.1 marks, then
      keep the bot running until grading is done — an unreachable bot at
      grading time scores zero on everything past that 0.1.

## Limitations

- Dataset discovery (when a question references a dataset without a direct
  URL) relies on the LLM's own knowledge or a follow-up search step; it isn't
  a general web crawler and can fail to find obscure or paywalled sources.
- The SQL-generation approach handles most tabular questions well but isn't
  guaranteed to succeed on very unusual schemas or multi-file joins the
  planner didn't anticipate (one automatic retry is attempted on failure).
- Conversation memory is in-process and in-memory — it resets on redeploy or
  restart, and won't survive across multiple server replicas without a
  shared store.

## Future work

- Persist conversation state and logs to a database instead of memory/local
  disk for multi-replica deployments.
- Add a lightweight retrieval step for dataset discovery (web search API)
  rather than relying solely on the model's own knowledge of dataset URLs.
- Cache downloaded datasets by URL to avoid re-downloading across repeated
  questions about the same source.
