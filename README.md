# AI Intelligence Ingestion Pipeline

## Implemented pipeline

This repository implements a provenance-first ingestion pipeline:

```text
async source adapters -> pooled HTTP acquisition -> immutable raw evidence
-> deterministic parsing and freshness gates -> canonical Pydantic records
-> optional LLM structured extraction -> PostgreSQL idempotent persistence
-> CSV/Google Sheets export
```

**Research** sources are arXiv (paginated API, 1,000 papers per run) and the official Papers with Code archive (1,000 paper-code links). **Startup** adapters cover Y Combinator (1,000 companies via Algolia API). **Product** adapters cover Product Hunt and There's An AI For That (1,000 products each). **News** RSS adapters monitor 5 AI sources (TechCrunch, VentureBeat, MIT Tech Review, OpenAI, Google AI) with a hard 24-hour freshness gate. **Job** RSS adapters monitor 5 AI job boards (Remote OK, We Work Remotely, Himalayas, Jobspresso, AI-Jobs.net) with the same freshness gate. Every accepted record links to raw evidence and no source fact is inferred without evidence.

News and job articles are enriched with **full-text extraction**: after RSS discovery, the pipeline fetches the original article/job page, extracts readable content via a multi-strategy HTML parser (JSON-LD, meta tags, `<article>`/`<p>` elements, `<time>` tags), and uses the extracted body if it is longer than the RSS description. For pages protected by **Cloudflare, Datadome, or JavaScript rendering**, a **Playwright headless browser** fallback activates automatically.

When LLM API keys are configured, the pipeline uses a **multi-tier LLM extraction** layer (Gemini → Groq → DeepSeek) with circuit breakers, adaptive 413 recovery, and exponential jittered retries to extract structured fields from each record.

## Design decisions

- `httpx.AsyncClient` is shared, connection-pooled, concurrency-bounded, timeout-aware, and retries only timeouts/network errors, HTTP 429, and 5xx responses. Backoff is bounded exponential with jitter and respects valid `Retry-After` values.
- Raw response bytes are written before parsing to content-addressed files beneath `data/raw/`; metadata records transport and retrieval details.
- Canonical record IDs are `SHA-256(source_id + canonical_url)` and PostgreSQL additionally enforces `UNIQUE (source_id, canonical_url)`. Retrying the same item cannot create a second canonical record.
- PostgreSQL is the system of record. The local raw store is deliberately behind a small boundary so it can be replaced by S3/GCS later.
- PWC archive rows are restricted to explicitly marked official implementations. GitHub metadata is cached by normalized repository URL within a run, including concurrent callers, so repeated paper-to-repository associations cause one GitHub API call.
- LLM extraction uses semantic chunking, schema validation, provider fallback, circuit breakers, adaptive 413 recovery, and exponential jittered retries for 429/network failures.
- Startup and product records can resolve against a seeded alias table. Every resolution is append-only in the mapping log, including unresolved and review cases.
- News and job adapters perform full-text extraction from original article pages. When HTTP fetch returns anti-bot challenges or insufficient content, a Playwright headless browser automatically retries the request.

## Setup

Python 3.12+ is required.

```bash
python -m pip install -e ".[dev]"
docker compose up -d postgres
```

### Playwright setup (for anti-bot bypass)

```bash
pip install playwright
playwright install chromium
```

### LLM extraction setup (optional)

Set one or more API keys to enable LLM-augmented extraction:

```bash
# Any combination of these enables the multi-tier fallback chain
export GEMINI_API_KEY="your-key"
export GROQ_API_KEY="your-key"
export DEEPSEEK_API_KEY="your-key"
```

Without API keys, the pipeline uses deterministic parsers only.

### Database setup

Set `DATABASE_URL` in your environment (use `.env.example` as the value template):

```bash
# PowerShell: $env:DATABASE_URL = "postgresql://pipeline:pipeline@localhost:5432/ai_intelligence"
# POSIX shell: export DATABASE_URL=postgresql://pipeline:pipeline@localhost:5432/ai_intelligence
```

## Usage

### Run the complete pipeline end-to-end

```bash
python -m src.main run-all
```

This executes all 6 steps sequentially: research → startups → products → news → jobs → CSV export.

### Run individual verticals

```bash
# Research papers (arXiv: 1,000 papers, paginated in batches of 100)
python -m src.main ingest-arxiv

# Research papers (Papers with Code: 1,000 paper-code links)
# Requires GITHUB_TOKEN for sustained GitHub API throughput.
python -m src.main ingest-papers-with-code

# Startups (Y Combinator: 1,000 companies via Algolia API)
python -m src.main ingest-startups

# Products (Product Hunt + There's An AI For That: 1,000 each)
python -m src.main ingest-products

# News (5 AI sources, 24-hour freshness gate, full-text extraction)
python -m src.main ingest-news

# Jobs (5 AI job boards, 24-hour freshness gate, full-text extraction)
python -m src.main ingest-jobs

# LLM extraction demo (requires at least one LLM API key)
python -m src.main extract-llm
```

### Export

```bash
# Export all 6 tabs to CSV files in data/export/
python -m src.main export-csv

# Export to Google Sheets (requires credentials)
export GOOGLE_SHEETS_SPREADSHEET_ID="your-spreadsheet-id"
export GOOGLE_SHEETS_ACCESS_TOKEN="your-access-token"
python -m src.main export-sheets
```

## Verification

```bash
python -m pytest
```

Tests cover successful async acquisition, timeout retry, URL canonicalization, content hashing, schema acceptance/rejection, raw-evidence persistence, duplicate prevention, and cached GitHub star enrichment.

## Architecture

The architecture deliverable is available at [architecture.pdf](architecture.pdf). The source-generation script is [scripts/generate_architecture_pdf.py](scripts/generate_architecture_pdf.py).
