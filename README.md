# Executive Productivity Agent

An AI-powered assistant that extracts, deduplicates, and tracks commitments from an executive's work-week inputs (meetings, emails, calendars, voice notes), then produces daily action briefs and answers natural-language questions.

## Features

- **Fixed offline dataset** — reads a static `data/sources.json` file containing one work week (Mon 21 Sep – Fri 25 Sep 2026).
- **Commitment extraction** — uses OpenRouter API (with Gemini Flash 1.5) to parse action items from multiple source types.
- **Smart deduplication** — merges duplicate commitments mentioned across sources, preserving full traceability.
- **Daily action brief** — generates a prioritised Markdown brief (overdue, due today, upcoming, completed).
- **Q&A interface** — chat with the agent about deadlines, priorities, and ownership.
- **Configurable "today"** — all overdue/upcoming logic adjusts dynamically based on a user-supplied reference date.

## Quick Start

### 1. Prerequisites

- **Python 3.10+**

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```


### 3. Run the Pipeline (CLI)

Extract commitments from `data/sources.json`:

```bash
python run_pipeline.py
```

This will:
- Load all sources (meeting transcripts, emails, calendars, voice notes).
- Extract commitments using OpenRouter/Gemini (results are cached per source).
- Deduplicate across sources.
- Save the final list to `data/commitments.json`.

Options:
```bash
python run_pipeline.py --clear-cache   # Force full re-extraction
python run_pipeline.py --today 2026-09-23  # Use a different reference date
```

### 4. Launch the Streamlit UI

```bash
streamlit run app.py
```

The web UI opens in your browser at `http://localhost:8501` with three tabs:

- **📋 Daily Brief** — Markdown-formatted action summary for "today".
- **💬 Q&A** — Chat interface to ask questions about commitments.
- **📊 Raw Data** — Inspect the full JSON commitment list.

Use the sidebar date picker to change "today" and see how overdue/upcoming statuses update in real time.

## Project Structure

```
aionos_ass_1/
├── data/
│   ├── sources.json          # Static input dataset (read-only)
│   └── commitments.json      # Generated output (gitignored)
├── prompts/
│   ├── system.txt            # Base system prompt for all LLM calls
│   ├── extract.txt           # Extraction prompt template
│   ├── dedupe.txt            # Deduplication prompt template
│   ├── brief.txt             # Daily brief generation prompt
│   └── qa.txt                # Q&A prompt template
├── src/
│   ├── loader.py             # Reads sources.json, yields one record per source
│   ├── gemini_client.py      # Wraps OpenRouter API with retries
│   ├── extractor.py          # Extracts commitments per source (cached)
│   ├── deduper.py            # Merges duplicate commitments
│   ├── dates.py              # Pure Python date resolution (no LLM)
│   ├── store.py              # Persists commitments + extraction cache
│   ├── brief.py              # Generates daily action brief
│   └── qa.py                 # Answers natural-language questions
├── app.py                    # Streamlit web UI
├── run_pipeline.py           # CLI pipeline runner
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── .gitignore
└── README.md
```

## How It Works

### Pipeline Flow

1. **Load sources** — `loader.iter_sources()` reads `data/sources.json` and yields one normalised record per source item.
2. **Extract commitments** — `extractor.extract_all()` calls OpenRouter API for each source. Results are cached by content hash, so re-runs skip unchanged sources.
3. **Resolve deadlines** — `dates.resolve_deadline()` converts natural-language strings like "Wednesday" or "EOD tomorrow" to real datetimes in pure Python (no LLM).
4. **Deduplicate** — `deduper.dedupe()` asks the LLM to group duplicate commitments, then merges their sources, deadlines, and descriptions.
5. **Store** — `store.save_commitments()` writes the final list to `data/commitments.json`.

### Daily Brief

`brief.generate_brief(today)` loads stored commitments, annotates each with a status (`overdue`, `due_today`, `upcoming`, `done`), and calls the LLM to produce a Markdown brief.

### Q&A

`qa.answer(question, today)` passes the user's question + annotated commitments to the LLM and returns a natural-language answer.

## Customisation

All prompts live in `prompts/` as plain-text files and are loaded at runtime. To customise the agent's behaviour:

1. Edit the prompt files (e.g. `prompts/extract.txt`, `prompts/brief.txt`).
2. Use placeholders like `{{SOURCE_JSON}}`, `{{PAYLOAD_JSON}}`, `{{QUESTION}}` — the code will substitute these at runtime.
3. Re-run the pipeline or refresh the UI to see changes.

## Data Shape

### Commitment Schema

Each commitment in `data/commitments.json` has:

```json
{
  "id": "commit-001",
  "title": "Send vendor list to Raghav",
  "description": "Updated vendor list promised during sync meeting",
  "owner": "Arjun Malhotra",
  "counterparty": "Raghav Sethi",
  "raw_deadline": "Wednesday morning",
  "deadline_iso": "2026-09-23T09:00:00",
  "completed": false,
  "sources": [
    {
      "source_id": "meeting-1",
      "source_type": "meeting_transcript",
      "timestamp": "2026-09-21T09:00:00"
    },
    {
      "source_id": "thread-1",
      "source_type": "email_thread",
      "timestamp": "2026-09-21T09:50:00"
    }
  ]
}
```

## Troubleshooting

### `OPENROUTER_API_KEY is not set`

Make sure you:
1. Created a `.env` file (copy from `.env.example`).
2. Added your OpenRouter API key from [OpenRouter Keys](https://openrouter.ai/keys).

### `Rate limit exceeded`

OpenRouter has rate limits. The code includes exponential backoff retries. If limits persist:
- Wait a few minutes and try again.
- Run with `--clear-cache` less frequently (the cache avoids redundant API calls).
- Check your OpenRouter credits at https://openrouter.ai/credits

### `JSON parse error`

The code retries up to 3 times automatically. If errors persist:
- Check your prompt files are well-formed.
- Try a different model by changing `MODEL_NAME` in `src/gemini_client.py`

## License

MIT — use however you like.
