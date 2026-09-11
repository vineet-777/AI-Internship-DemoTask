# AI Intelligence Ingestion Pipeline

## Implemented vertical slice

This repository currently implements one provenance-first research-paper ingestion slice:

```text
arXiv Atom API -> pooled async HTTP fetch -> immutable local raw evidence
-> deterministic Atom parsing -> URL/content identities -> Pydantic validation
-> PostgreSQL insert with database-enforced idempotency
```

The configured sources are arXiv's public Atom API and the officially published Papers with Code archive. PWC associates a paper with its explicit GitHub implementation; arXiv supplies author/publication metadata where PWC's association dump lacks it; GitHub's REST API supplies the current star count. Every HTTP response is retained as raw evidence and all of its raw-document IDs are carried in record provenance. No LLM is called, so no source fact is inferred or fabricated.

## Design decisions

- `httpx.AsyncClient` is shared, connection-pooled, concurrency-bounded, timeout-aware, and retries only timeouts/network errors, HTTP 429, and 5xx responses. Backoff is bounded exponential with jitter and respects valid `Retry-After` values.
- Raw response bytes are written before parsing to content-addressed files beneath `data/raw/`; metadata records transport and retrieval details.
- Canonical record IDs are `SHA-256(source_id + canonical_url)` and PostgreSQL additionally enforces `UNIQUE (source_id, canonical_url)`. Retrying the same item cannot create a second canonical record.
- PostgreSQL is the system of record. The local raw store is deliberately behind a small boundary so it can be replaced by S3/GCS later.
- PWC archive rows are restricted to explicitly marked official implementations. GitHub metadata is cached by normalized repository URL within a run, including concurrent callers, so repeated paper-to-repository associations cause one GitHub API call.

## Setup

Python 3.12+ is required.

```bash
python -m pip install -e ".[dev]"
docker compose up -d postgres
```

Set `DATABASE_URL` in your environment (use `.env.example` as the value template), then run:

```bash
# PowerShell: $env:DATABASE_URL = "postgresql://pipeline:pipeline@localhost:5432/ai_intelligence"
# POSIX shell: export DATABASE_URL=postgresql://pipeline:pipeline@localhost:5432/ai_intelligence
python -m src.main ingest-arxiv
# Requires GITHUB_TOKEN for sustained GitHub API throughput.
python -m src.main ingest-papers-with-code
```

The command creates its two required tables/indexes on first use. It requires a reachable PostgreSQL database; the Docker service is provided for local development.

## Verification

```bash
python -m pytest
```

Tests cover successful async acquisition, timeout retry, URL canonicalization, content hashing, schema acceptance/rejection, raw-evidence persistence, duplicate prevention, and cached GitHub star enrichment.

## Deliberately deferred

Additional sources and record types, queues/workers, freshness/watermarks, LLM providers/chunking/fallback, entity resolution, exports, and architecture PDF are later milestones. They are not claimed as implemented here.
