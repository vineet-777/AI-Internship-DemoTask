# AI Intelligence Ingestion Pipeline — Master Implementation Plan

## 0. Purpose

Build a production-oriented AI/data intelligence ingestion pipeline for the GraphOne / FrontierAtlas AI Engineer demo task.

The system must ingest, normalize, enrich, validate, deduplicate, resolve, and export intelligence about:

- Startups
- Products
- AI research papers
- AI jobs
- AI news

The implementation must prioritize:

1. Data provenance
2. Data quality
3. LLM reliability
4. Async/concurrent ingestion
5. Idempotency and deduplication
6. Freshness guarantees
7. Fault tolerance
8. Horizontal scalability
9. Maintainability
10. Observable, reproducible engineering

The assignment explicitly evaluates LLM orchestration (25%), data quality (25%), scale thinking (20%), engineering rigor (20%), and entity resolution (10%). Every record must trace to a legitimate source URL; hallucinated data can result in disqualification.

---

# 1. Source Requirements

Use the assignment as the source of truth for the mandatory minimums.

## Phase I — Bulk Acquisition

Minimum target:

- 1,000 unique startup records
- 1,000 unique product records
- 1,000 unique research-paper records
- Research papers must include associated GitHub repositories where available and current GitHub stars
- Design must theoretically scale to 500,000+ records without rewriting core application logic

## Phase II — Fresh Signal Ingestion

Monitor:

- 5 distinct AI news sources
- 5 distinct AI job boards

Freshness requirement:

- Every accepted news/job record must be demonstrably within the previous 24 hours relative to the ingestion run
- Parse absolute and relative dates
- Handle missing date metadata
- Preserve evidence about how the date was obtained
- Use a watermark / seen-state strategy to avoid reprocessing

## Phase III — LLM Extraction

Requirements:

- Multi-tier provider fallback
- 413/context-size protection
- 429/rate-limit handling
- Exponential backoff
- Jitter
- Structured output
- Application-side schema validation
- No fabricated values

Example provider chain:

1. Gemini Flash
2. Groq-hosted Llama
3. DeepSeek

Provider names and models must be configurable rather than hardcoded throughout the application.

## Phase IV — Entity Resolution

Canonicalize messy startup/product names, for example:

- OpenAI
- Open AI
- OpenAI Inc.
- OpenAI, Inc.
- OPENAI

All should map to the canonical entity `OpenAI` when supported by deterministic evidence.

Keep a complete raw-to-canonical mapping log.

## Phase V — Anti-Bot / High-Value Sources

Implement an adaptive acquisition strategy:

1. Official/public API or RSS when available
2. Async HTTP client
3. Playwright async browser for JS-rendered pages
4. Cached previously acquired content
5. Controlled failure/quarantine when a source cannot be acquired

Do not claim to defeat security controls. The system should demonstrate responsible, bounded handling of JS-heavy/protected sources.

## Phase VI — Production Design

The final architecture document must cover:

1. How the system scales to 500k+ records
2. Exact 413 and 429 handling
3. Duplicate prevention across distributed workers
4. Primary DB plus vector/graph storage strategy

---

# 2. Core Engineering Principles

## 2.1 Provenance First

Every record must retain:

- Source name
- Original URL
- Canonical URL
- Retrieval timestamp
- Raw content identifier/hash
- Extraction method
- LLM provider/model if an LLM was used
- Validation status
- Entity-resolution status

Never let the LLM invent a URL, publication date, GitHub repository, company, metric, or other source fact.

The system should follow:

```text
source
  -> fetch
  -> preserve raw evidence
  -> deterministic parsing
  -> semantic extraction where required
  -> validation
  -> canonicalization
  -> storage
  -> export
```

## 2.2 Deterministic Before Probabilistic

Use deterministic methods whenever practical:

- JSON-LD / meta tags for dates
- CSS/XPath selectors for known fields
- GitHub API for star counts
- URL canonicalization
- regex for obvious numeric values
- Pydantic / JSON Schema for validation
- database uniqueness constraints for idempotency

Use LLMs only for semantic interpretation that deterministic extraction cannot reliably perform.

## 2.3 Never Silently Repair Bad Data

When extraction is uncertain:

```text
accept
review
quarantine
reject
```

Do not silently create a plausible value.

---

# 3. Recommended Technology Stack

## Runtime

- Python 3.12+
- asyncio
- typing
- dataclasses where appropriate

## HTTP / Crawling

- `httpx` or `aiohttp`
- BeautifulSoup
- `trafilatura` for article/main-content extraction
- Playwright async for JS-rendered pages

Prefer one primary async HTTP client and keep the fetch layer behind an interface.

## Validation

- Pydantic v2
- JSON Schema where useful

## Database

Primary:

- PostgreSQL

Recommended use:

- canonical entities
- source metadata
- crawl runs
- ingestion state
- entity mappings
- idempotency
- validation status

## Raw Storage

For the demo:

- local filesystem abstraction

Production design:

- S3/GCS-compatible object storage

Keep storage behind an interface so the implementation can migrate without rewriting pipeline code.

## Vector Store

Recommended:

- Qdrant or Chroma

Use primarily for semantic retrieval/discovery rather than as the system-of-record.

## Graph

Recommended:

- Neo4j for the demonstration architecture

Represent relationships such as:

```text
Startup -> Product
Startup -> Founder
Research Paper -> GitHub Repository
Startup -> News Article
Company -> Job Posting
Research Paper -> Technology
```

Graph integration can be implemented minimally for the demo while keeping the interface production-oriented.

## Queue

For local/demo:

- Redis + queue abstraction

Production architecture:

- Redis Streams, RabbitMQ, Kafka, or equivalent durable queue

Do not couple business logic tightly to one broker.

## Configuration

- YAML/TOML configuration
- environment variables for secrets

Example:

```text
configs/
  sources.yaml
  models.yaml
  settings.yaml
```

## Tests

- pytest
- pytest-asyncio
- HTTP mocking as needed

## Containerization

- Docker
- docker-compose for local services

---

# 4. Repository Structure

Create:

```text
ai-intelligence-pipeline/
├── README.md
├── architecture.pdf
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
│
├── configs/
│   ├── sources.yaml
│   ├── models.yaml
│   └── settings.yaml
│
├── src/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── startup.py
│   │   ├── product.py
│   │   ├── research.py
│   │   ├── job.py
│   │   └── news.py
│   │
│   ├── crawlers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── startup/
│   │   ├── product/
│   │   ├── research/
│   │   ├── news/
│   │   └── jobs/
│   │
│   ├── fetch/
│   │   ├── __init__.py
│   │   ├── http_client.py
│   │   ├── browser_client.py
│   │   ├── retry.py
│   │   ├── rate_limiter.py
│   │   └── circuit_breaker.py
│   │
│   ├── parsing/
│   │   ├── html.py
│   │   ├── structured_data.py
│   │   ├── content.py
│   │   └── dates.py
│   │
│   ├── extraction/
│   │   ├── orchestrator.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── gemini.py
│   │   │   ├── groq.py
│   │   │   └── deepseek.py
│   │   ├── chunker.py
│   │   ├── prompts.py
│   │   ├── merge.py
│   │   └── validators.py
│   │
│   ├── entities/
│   │   ├── normalizer.py
│   │   ├── matcher.py
│   │   ├── aliases.py
│   │   └── mapping_store.py
│   │
│   ├── freshness/
│   │   ├── watermark.py
│   │   ├── dedupe.py
│   │   └── policies.py
│   │
│   ├── storage/
│   │   ├── base.py
│   │   ├── postgres.py
│   │   ├── object_store.py
│   │   ├── vector.py
│   │   └── graph.py
│   │
│   ├── jobs/
│   │   ├── queue.py
│   │   ├── workers.py
│   │   └── tasks.py
│   │
│   ├── observability/
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   └── tracing.py
│   │
│   └── export/
│       ├── sheets.py
│       └── csv.py
│
├── tests/
│   ├── unit/
│   │   ├── test_dates.py
│   │   ├── test_entity_resolution.py
│   │   ├── test_chunking.py
│   │   ├── test_retry.py
│   │   ├── test_dedupe.py
│   │   └── test_validation.py
│   │
│   ├── integration/
│   │   ├── test_research_pipeline.py
│   │   ├── test_news_freshness.py
│   │   └── test_llm_fallback.py
│   │
│   └── fixtures/
│
├── scripts/
│   ├── seed_entities.py
│   ├── run_bulk.py
│   ├── run_freshness.py
│   ├── benchmark.py
│   └── export_sheets.py
│
└── data/
    ├── raw/
    ├── normalized/
    ├── cache/
    └── exports/
```

---

# 5. Configuration Design

## 5.1 `sources.yaml`

Make source behavior data-driven.

Example:

```yaml
sources:
  - id: source_a
    type: news
    mode: http
    enabled: true
    listing_url: "https://example.com/ai"
    article_selector: "article a"
    date_selectors:
      - 'meta[property="article:published_time"]'
      - 'time[datetime]'
    content_selector: "article"

  - id: source_b
    type: news
    mode: playwright
    enabled: true
    listing_url: "https://example.com/news"

  - id: research_a
    type: research
    mode: api
    enabled: true
```

No source-specific logic should leak into unrelated pipeline layers.

## 5.2 `models.yaml`

```yaml
providers:
  gemini:
    enabled: true
    model: "CONFIGURE_AT_RUNTIME"
    max_concurrency: 10
    timeout_seconds: 30

  groq:
    enabled: true
    model: "CONFIGURE_AT_RUNTIME"
    max_concurrency: 10
    timeout_seconds: 30

  deepseek:
    enabled: true
    model: "CONFIGURE_AT_RUNTIME"
    max_concurrency: 8
    timeout_seconds: 30
```

Never hardcode model limits into business logic.

## 5.3 `settings.yaml`

```yaml
crawler:
  max_concurrency: 50
  request_timeout_seconds: 20
  max_retries: 4

freshness:
  max_age_hours: 24

llm:
  max_retries_per_provider: 2
  jitter_seconds: 1.0
  chunk_target_tokens: 5000

storage:
  batch_size: 250
```

---

# 6. Common Record Metadata

Every canonical record should carry shared provenance.

Suggested common fields:

```json
{
  "record_id": "stable-unique-id",
  "schemaVersion": "1.0",
  "recordType": "STARTUP",
  "source": {
    "name": "source-name",
    "url": "original-source-url",
    "canonicalUrl": "canonicalized-url"
  },
  "collectedAt": "2026-09-11T00:00:00Z",
  "provenance": {
    "retrievedAt": "2026-09-11T00:00:00Z",
    "contentHash": "sha256...",
    "extractionMethod": "deterministic+llm",
    "llmProvider": "gemini",
    "llmModel": "configured-model",
    "validationStatus": "VALID"
  }
}
```

Do not remove assignment-required fields just because extra metadata is added.

---

# 7. Required Canonical Schemas

## 7.1 Startup

Minimum assignment fields:

```json
{
  "schemaVersion": "1.0",
  "recordType": "STARTUP",
  "source": {
    "name": "...",
    "url": "..."
  },
  "content": {
    "entityName": "...",
    "data": {
      "employeeCount": 100
    }
  },
  "collectedAt": "ISO-8601 timestamp"
}
```

Recommended extra fields:

- description
- headquarters
- website
- founded_year
- funding
- canonical_entity_id
- raw_entity_name
- resolution_confidence

Only populate fields supported by source evidence.

## 7.2 Product

Minimum assignment fields:

```json
{
  "schemaVersion": "1.0",
  "recordType": "PRODUCT",
  "source": {
    "name": "...",
    "url": "..."
  },
  "content": {
    "startupName": "...",
    "pricingModel": "FREE|FREEMIUM|PAID|ENTERPRISE"
  },
  "collectedAt": "ISO-8601 timestamp"
}
```

## 7.3 Research Paper

Minimum fields:

```json
{
  "schemaVersion": "1.0",
  "recordType": "RESEARCH_PAPER",
  "content": {
    "title": "...",
    "authors": [],
    "paper_url": "...",
    "github_url": "...",
    "github_stars": 123,
    "published_date": "ISO-8601 timestamp"
  }
}
```

GitHub stars must come from a legitimate GitHub data source/API, not an LLM estimate.

## 7.4 Job

Minimum fields:

```json
{
  "schemaVersion": "1.0",
  "recordType": "JOB",
  "content": {
    "company": "...",
    "date": "ISO-8601 timestamp",
    "is_remote": true,
    "role_family": "Engineering"
  }
}
```

The `date` must pass the 24-hour freshness gate.

## 7.5 News

The assignment does not prescribe a full News schema, so design one consistent with the system:

```json
{
  "schemaVersion": "1.0",
  "recordType": "NEWS",
  "source": {
    "name": "...",
    "url": "..."
  },
  "content": {
    "title": "...",
    "published_date": "...",
    "author": "...",
    "body": "...",
    "category": "AI"
  },
  "freshness": {
    "age_hours": 4.2,
    "date_source": "json_ld",
    "date_confidence": 0.99,
    "is_fresh": true
  },
  "collectedAt": "..."
}
```

---

# 8. Fetch Layer

## 8.1 Async HTTP

Use a shared client with:

- connection pooling
- timeout
- concurrency semaphore
- per-host rate limiting
- retries
- structured logging

Avoid creating one client per request.

## 8.2 Browser Layer

Use Playwright only for sources that require JS rendering.

Requirements:

- reuse browser/context where practical
- bounded concurrency
- navigation timeout
- content extraction timeout
- cleanup on task completion
- explicit failure classification

Do not run Playwright for every normal HTML page.

## 8.3 Response classification

Classify failures:

```text
SUCCESS
REDIRECT
NOT_FOUND
FORBIDDEN
RATE_LIMITED
SERVER_ERROR
TIMEOUT
PARSING_ERROR
BROWSER_ERROR
UNKNOWN
```

This enables meaningful metrics and retry policies.

---

# 9. Retry System

Implement a shared retry utility.

Retry candidates:

- timeouts
- transient network errors
- 429
- 5xx

Do not blindly retry:

- malformed URLs
- 404
- permanent validation failures

Backoff formula:

```text
delay = min(max_delay, base_delay * 2^attempt)
delay += random_jitter
```

Respect `Retry-After` when present.

Record:

- attempt number
- status
- delay
- final outcome

---

# 10. Rate Limiting

Use independent rate limiters for:

- each LLM provider
- GitHub
- each high-volume source where required

Do not use one global semaphore for unrelated services.

Use:

```text
provider
  -> limiter
  -> circuit breaker
  -> request
```

Keep limits configurable.

Track token/request usage where provider metadata supports it.

---

# 11. Circuit Breaker

Implement states:

```text
CLOSED
  |
  | repeated failures
  v
OPEN
  |
  | cooldown
  v
HALF_OPEN
  |
  | success
  v
CLOSED
```

When a provider becomes unhealthy:

- stop hammering the provider
- route new requests to fallback providers
- periodically test recovery

---

# 12. Bulk Crawler Architecture

Use:

```text
discovery
  -> URL normalization
  -> URL dedupe
  -> job queue
  -> async workers
  -> fetch
  -> parse
  -> persist
```

Workers must be stateless.

Concurrency should be configuration-driven.

Avoid module-level mutable state.

---

# 13. Source Adapter Interface

Define something similar to:

```python
class SourceAdapter(ABC):
    @abstractmethod
    async def discover(self) -> list[str]:
        ...

    @abstractmethod
    async def fetch(self, url: str) -> RawResponse:
        ...

    @abstractmethod
    async def parse(self, response: RawResponse) -> list[dict]:
        ...
```

For sources where a generic implementation is sufficient, reuse a base adapter.

For unusual sources, create a dedicated adapter.

---

# 14. Research-Paper Pipeline

Pipeline:

```text
Paper index/API
    -> paper metadata
    -> canonical paper URL
    -> repository discovery
    -> GitHub URL normalization
    -> GitHub API
    -> current stars
    -> schema validation
    -> storage
```

Do not rely on HTML scraping of GitHub when a legitimate API path is available.

## GitHub cache

Cache repository metadata by normalized repository URL.

If multiple papers reference the same repository:

```text
paper A
paper B
paper C
      \
       -> same repo cache entry
             -> one API fetch
```

This saves rate budget and improves throughput.

---

# 15. News and Jobs Freshness Engine

## Date-source priority

Try sources in a deliberate order:

1. JSON-LD `datePublished`
2. OpenGraph/meta fields
3. `<time datetime>`
4. source-specific selectors
5. RSS timestamp
6. visible date text
7. relative-time parsing

Store the chosen date source.

## Date normalization

Normalize all times to UTC internally.

Example:

```text
"2 hours ago"
    -> absolute timestamp

"Yesterday"
    -> source-local date/time policy

"Sep 11"
    -> infer year using run date and source context
```

Do not guess silently.

If confidence is too low:

```text
quarantine
```

rather than accepting the record as fresh.

## Freshness gate

For each candidate:

```text
published_at
    ->
age = now_utc - published_at
    ->
0 <= age <= 24h
```

Only records passing this gate enter the final fresh News/Jobs export.

Also reject future timestamps unless a source-specific clock skew policy explains them.

---

# 16. Watermarks and Duplicate Prevention

Use multiple layers.

## Layer 1 — URL canonicalization

Normalize:

- scheme where appropriate
- hostname casing
- tracking query parameters
- fragments
- trailing slash rules

Do not strip query parameters blindly if they change content identity.

## Layer 2 — URL identity hash

```text
idempotency_key = SHA256(source_id + canonical_url)
```

## Layer 3 — content hash

Hash normalized article/entity content.

This identifies duplicate content served under different URLs.

## Layer 4 — database uniqueness

Use DB constraints such as:

```text
UNIQUE(source_id, canonical_url)
```

or an appropriate deterministic identity key.

## Distributed safety

Never rely solely on:

```python
seen = set()
```

because that fails across workers/processes.

---

# 17. Raw Content Preservation

Before LLM processing, persist a raw representation:

```text
raw HTML
raw JSON
retrieved_at
source URL
content hash
HTTP metadata
```

The raw artifact should be reproducible and linked to the canonical record.

Production design:

```text
object storage
  /source/year/month/day/content_hash
```

Demo may use:

```text
data/raw/
```

behind a storage abstraction.

---

# 18. Content Normalization

Remove noise before LLM invocation:

- navigation
- footer
- cookie banners
- advertisements
- duplicate sidebars
- comments when irrelevant
- tracking scripts
- hidden HTML

Keep semantically important content.

Produce:

```text
title
headings
paragraphs
lists
tables where useful
metadata
```

Prefer content extraction based on document structure rather than blind character truncation.

---

# 19. Intelligent Chunking

Never implement the core 413 strategy as:

```python
text[:10000]
```

Instead:

```text
raw HTML
  -> clean text
  -> headings/paragraphs
  -> token estimation
  -> semantic sections
  -> pack under target token budget
```

Chunk metadata should include:

```json
{
  "chunk_id": "...",
  "source_record_id": "...",
  "section": "...",
  "token_estimate": 4800,
  "sequence": 3
}
```

## Chunk strategy

Prefer:

```text
heading boundary
paragraph boundary
sentence boundary
```

in that order.

Avoid splitting inside structured fields when possible.

## Multi-chunk extraction

```text
document
  -> chunk 1 -> extraction
  -> chunk 2 -> extraction
  -> chunk N -> extraction
  -> deterministic merge
  -> final schema validation
```

Only merge facts supported by source chunks.

---

# 20. LLM Orchestrator

Create a provider-neutral interface:

```python
class LLMProvider(ABC):
    @abstractmethod
    async def extract(
        self,
        prompt: str,
        schema: type[BaseModel],
    ) -> ExtractionResult:
        ...
```

The orchestrator controls:

- token estimation
- prompt construction
- provider selection
- rate limiting
- retries
- fallback
- circuit breaking
- structured parsing
- schema validation
- logging

Do not put provider-specific branching throughout the application.

---

# 21. Provider Selection

Initial chain:

```text
Gemini
  -> Groq
  -> DeepSeek
```

But make it adaptive.

Track:

- availability
- recent failure rate
- latency
- remaining budget if known
- rate-limit state

Conceptual flow:

```text
request
  -> choose healthy provider
  -> attempt
  -> success?
       yes -> validate -> return
       no  -> classify -> retry/fallback
```

---

# 22. LLM 429 Handling

When a provider returns 429:

1. Read retry metadata if available
2. Wait using exponential backoff + jitter
3. Reattempt within provider retry budget
4. If still failing, route to next provider
5. Update provider health
6. Record the event

Do not enter an infinite retry loop.

Suggested state:

```text
provider_attempts = 0..N
global_fallback_budget = bounded
```

---

# 23. LLM 413 / Context-Overflow Handling

Treat oversized inputs as a routing problem.

```text
request
  -> estimate tokens
  -> under limit?
       yes -> provider
       no  -> semantic chunking
                -> parallel extraction
                -> merge
                -> validate
```

Do not repeatedly retry an oversized payload unchanged.

If a provider still returns a 413:

```text
reduce chunk size
retry once
```

and/or route to a provider with a compatible context budget.

---

# 24. Structured Extraction Prompts

Prompts should require:

- Return only structured data
- Do not infer missing facts
- Use `null`/empty values when evidence is absent
- Do not invent URLs
- Preserve source wording where needed
- Extract only facts present in supplied content

Important rule:

```text
Missing source evidence != permission to guess
```

---

# 25. Schema Validation

Every LLM result must pass:

```text
JSON parse
  -> Pydantic validation
  -> domain validation
  -> provenance validation
  -> accept/reject
```

Examples:

```text
PRODUCT.pricingModel must be one of:
FREE
FREEMIUM
PAID
ENTERPRISE
```

Research paper:

```text
github_stars >= 0
published_date is valid timestamp
```

Job/news:

```text
publication date required for final fresh export
```

---

# 26. Entity Resolution Engine

Use layered matching.

## Stage 1 — Unicode normalization

- Unicode normalize
- lowercase
- trim
- collapse whitespace

## Stage 2 — punctuation normalization

Remove irrelevant punctuation.

## Stage 3 — legal suffix normalization

Handle forms such as:

- Inc.
- Inc
- Ltd.
- Limited
- LLC
- Corp.
- Corporation

Do not remove legitimate business words blindly.

## Stage 4 — alias table

Example:

```text
raw_name -> canonical_name
open ai -> OpenAI
openai inc -> OpenAI
```

## Stage 5 — exact normalized match

## Stage 6 — fuzzy candidate generation

Only run fuzzy matching against reasonable candidates.

## Stage 7 — confidence policy

Example policy:

```text
1.00          -> exact/normalized exact
>= 0.95       -> automatic match
0.80–0.95     -> review/quarantine depending on context
< 0.80        -> unresolved
```

Thresholds must be configurable and benchmarked.

Never force a low-confidence entity match.

---

# 27. Entity Mapping Log

Produce:

```text
raw_name
canonical_name
source
method
confidence
timestamp
record_id
```

Example:

```csv
Open AI,OpenAI,normalization,1.00,2026-09-11T...
OpenAI Inc.,OpenAI,suffix_removal,0.99,2026-09-11T...
```

This becomes the final Google Sheets `Entity Mapping Log` tab.

---

# 28. Storage Model

## PostgreSQL tables

Minimum conceptual tables:

```text
sources
crawl_runs
raw_documents
startups
products
research_papers
jobs
news
entity_aliases
entity_mappings
github_repositories
ingestion_events
```

## Suggested relationship

```text
sources
  -> raw_documents
      -> canonical entity records
```

Use foreign keys and uniqueness where practical.

## Indexes

Index:

- canonical URL
- source + canonical URL
- record type
- publication date
- canonical entity ID
- crawl run ID
- idempotency key

---

# 29. Vector Store Strategy

Use vector storage for semantic retrieval, discovery, and similarity.

Example embeddings:

```text
research paper abstract
startup description
product description
news article
job description
```

Attach metadata:

```json
{
  "record_id": "...",
  "record_type": "RESEARCH_PAPER",
  "source": "arxiv"
}
```

Vector DB is not the authoritative system of record.

---

# 30. Graph Strategy

Model:

```text
(:Startup)-[:BUILDS]->(:Product)
(:Startup)-[:MENTIONED_IN]->(:News)
(:Startup)-[:POSTS]->(:Job)
(:Paper)-[:IMPLEMENTS]->(:GitHubRepository)
(:Paper)-[:ABOUT]->(:Technology)
```

Start with a small working subset.

Prioritize correct identifiers and provenance over a huge graph.

---

# 31. Queue and Worker Model

Use jobs such as:

```text
DISCOVER_SOURCE
FETCH_URL
PARSE_DOCUMENT
EXTRACT_ENTITY
RESOLVE_ENTITY
FETCH_GITHUB
EXPORT_RECORD
```

Each task should be:

- small
- idempotent
- retryable
- observable

Worker architecture:

```text
queue
  -> worker
       -> execute
       -> persist
       -> ACK

failure
  -> retry
  -> dead-letter/quarantine after budget
```

Production scale:

```text
more queue partitions
+
more stateless workers
```

No code rewrite.

---

# 32. Error Classification

Create explicit categories:

```text
NETWORK_TRANSIENT
RATE_LIMIT
CONTEXT_TOO_LARGE
PROVIDER_UNAVAILABLE
PARSING_FAILURE
SCHEMA_FAILURE
DATE_UNRESOLVED
ENTITY_UNRESOLVED
SOURCE_BLOCKED
AUTH_FAILURE
PERMANENT_NOT_FOUND
```

Use categories to determine retry vs quarantine vs reject.

---

# 33. Observability

Structured logs should contain fields such as:

```text
timestamp
run_id
task_id
source_id
url
record_id
record_type
attempt
status
latency_ms
provider
model
error_category
```

Metrics should include:

```text
crawl_requests_total
crawl_success_total
crawl_failure_total
http_429_total
http_403_total
http_413_total

llm_requests_total
llm_success_total
llm_fallback_total
llm_validation_failures_total

records_extracted_total
records_rejected_total
records_quarantined_total
duplicates_prevented_total

fresh_records_total
stale_records_total

entity_auto_match_total
entity_unresolved_total
```

---

# 34. Benchmarking

Create a benchmark command:

```bash
python scripts/benchmark.py
```

Output:

```text
Run ID: ...
Records attempted: ...
Records accepted: ...
Records rejected: ...
Runtime: ...
Throughput: ...
HTTP success rate: ...
429 recovered: ...
LLM fallback count: ...
Schema failure count: ...
Duplicate prevention count: ...
Freshness pass rate: ...
Entity match rate: ...
```

Do not invent benchmark numbers.

Only document measurements from real runs.

---

# 35. Testing Plan

## Date Tests

Test at minimum:

```text
"2 hours ago"
"15 minutes ago"
"Yesterday"
"Sep 11"
"Sep 11, 2026"
ISO-8601
timezone-aware timestamps
missing metadata
invalid date
future date
```

## Entity Tests

```text
OpenAI
Open AI
OPENAI
OpenAI Inc.
OpenAI, Inc.
```

Include negative cases where similar names must remain separate.

## Chunking Tests

Test:

- below limit
- exactly at limit
- just above limit
- very large document
- headings
- tables
- paragraphs
- empty sections

## Retry Tests

Mock:

```text
200
429
429 -> 200
500 -> 200
timeout -> success
413
permanent 404
```

## LLM Fallback Tests

Test:

```text
Gemini success
Gemini 429 -> retry -> success
Gemini unavailable -> Groq
Gemini + Groq fail -> DeepSeek
all providers fail
invalid JSON
valid JSON with invalid schema
```

## Freshness Tests

Test:

```text
23h59m old -> ACCEPT
24h exactly -> policy-defined boundary
24h01m old -> REJECT
future -> REJECT
unknown date -> QUARANTINE
```

## Idempotency Tests

Run the same job twice.

Expected:

```text
first run -> insert
second run -> no duplicate canonical records
```

---

# 36. Data Quality Gates

Before export, enforce:

## Startup

- valid source URL
- non-empty canonical name
- schema valid

## Product

- valid source URL
- valid startup relationship if claimed
- valid pricing enum

## Research

- title
- paper URL
- authors if available
- publication date
- GitHub URL if available
- GitHub stars verified when GitHub URL exists

## News

- title
- source URL
- publication date
- freshness <= 24h

## Jobs

- company
- publication date
- freshness <= 24h
- role family where extractable

Any record failing a hard gate goes to quarantine/rejection, not final export.

---

# 37. Source Selection Strategy

Do not choose ten sources that all behave the same.

Select sources that exercise different mechanisms.

Desired coverage:

```text
Source type       Example behavior
-----------------------------------
Clean HTML        standard HTTP
RSS               timestamp-rich
JSON-LD           structured metadata
JS-rendered       browser required
Pagination        multi-page discovery
Relative dates    "2 hours ago"
Weak dates        missing metadata
High-volume       concurrency test
```

The exact sources should be verified for current accessibility before implementation.

---

# 38. Anti-Bot Strategy

Implement the acquisition hierarchy:

```text
1. Official API / RSS / public structured source
2. HTTP fetch
3. Playwright async
4. cached content
5. controlled failure/quarantine
```

For difficult sources:

- keep browser concurrency low
- reuse sessions
- use explicit timeouts
- avoid excessive navigation
- cache results
- respect site restrictions and terms
- record blocked-source statistics
- do not fabricate unavailable records

A protected source that cannot be legitimately acquired is better represented as a documented limitation than as invented data.

---

# 39. Caching

Implement caches for:

- HTTP content
- parsed source metadata
- GitHub repository metadata
- LLM results where safe and deterministic
- entity resolution candidates

Cache key:

```text
source_id + canonical_url + relevant request version
```

For mutable metrics such as GitHub stars, include a freshness policy rather than treating cached values as permanently current.

---

# 40. Export Pipeline

Do not use Google Sheets as the primary database.

Pipeline:

```text
PostgreSQL
   -> query validated records
   -> final export validation
   -> Google Sheets
```

Required tabs:

1. Startups
2. Products
3. Research Papers
4. Jobs
5. News
6. Entity Mapping Log

Recommended export columns include provenance where practical.

---

# 41. Google Sheets Requirements

Minimum:

- public/shareable sheet
- six tabs
- clean headers
- no malformed JSON
- no duplicate rows
- no fabricated records
- timestamps normalized consistently

Use a batch export rather than row-by-row API calls whenever possible.

---

# 42. README Requirements

README structure:

```markdown
# AI Intelligence Ingestion Pipeline

## Overview
## Problem
## Architecture
## Design Principles
## Repository Structure
## Source Strategy
## Async Crawling
## Freshness System
## LLM Orchestration
## 413 Handling
## 429 Handling
## Entity Resolution
## Provenance
## Storage
## Scale to 500k+
## Observability
## Testing
## Benchmark Results
## Known Limitations
## Setup
## Configuration
## Running Bulk Ingestion
## Running Freshness Ingestion
## Exporting Results
```

Do not claim capabilities that have not been implemented.

---

# 43. Architecture PDF — Maximum 3 Pages

## Page 1 — End-to-End Architecture

Large, readable diagram:

```text
Sources
   ↓
Discovery
   ↓
Queue
   ↓
Async Workers
   ↓
Fetch / Browser
   ↓
Raw Store
   ↓
Normalize
   ↓
Freshness Gate
   ↓
LLM Router
   ↓
Validation
   ↓
Entity Resolution
   ↓
PostgreSQL
   ├── Vector Store
   └── Graph Store
   ↓
Google Sheets
```

Keep labels concise.

## Page 2 — Reliability

Show two flows:

```text
413
 -> token estimate
 -> semantic chunking
 -> extraction
 -> merge
 -> validate
```

and:

```text
429
 -> Retry-After
 -> exponential backoff + jitter
 -> provider limiter
 -> retry budget
 -> fallback provider
 -> circuit breaker
```

## Page 3 — Scale + Freshness

Show:

```text
500k+
 -> partitioned queue
 -> stateless workers
 -> horizontal scale
 -> shared durable storage
```

and:

```text
source URL
 -> canonical URL
 -> idempotency key
 -> DB uniqueness
```

plus:

```text
publication date
 -> normalization
 -> freshness gate
 -> watermark
 -> fresh export
```

---

# 44. Three-Day Execution Order

The time box is three days. Optimize for a reliable vertical slice before expanding coverage.

## Day 1 — Foundation + Bulk Ingestion

### Step 1
Create project/repository structure.

### Step 2
Implement configuration and logging.

### Step 3
Implement common schemas.

### Step 4
Implement async fetch layer.

### Step 5
Implement retry, timeout, rate-limiter abstractions.

### Step 6
Implement raw storage.

### Step 7
Implement URL canonicalization and content hashing.

### Step 8
Implement startup adapter.

### Step 9
Implement product adapter.

### Step 10
Implement research-paper adapter.

### Step 11
Implement GitHub client + cache.

### Step 12
Produce first end-to-end batch.

Target checkpoint:

```text
100 startups
100 products
100 research papers
```

with valid provenance.

Do not proceed to large-scale scraping until the vertical slice is reliable.

---

# 45. Day 1 Definition of Done

All of the following must work:

```text
source -> fetch -> parse -> validate -> store
```

Requirements:

- async
- retries
- logs
- raw evidence
- deterministic IDs
- schema validation
- no fabricated values

---

# 46. Day 2 — Freshness + LLM + Entity Resolution

### Step 1
Implement date parser.

### Step 2
Implement freshness gate.

### Step 3
Implement watermarks and deduplication.

### Step 4
Implement five news adapters.

### Step 5
Implement five job adapters.

### Step 6
Implement provider interface.

### Step 7
Implement Gemini adapter.

### Step 8
Implement Groq adapter.

### Step 9
Implement DeepSeek adapter.

### Step 10
Implement orchestrator.

### Step 11
Implement 413-aware chunking.

### Step 12
Implement 429 retry/fallback.

### Step 13
Implement circuit breaker.

### Step 14
Implement entity normalization.

### Step 15
Implement canonical matching + mapping log.

### Step 16
Add tests for dates, LLM failures, entity matching.

---

# 47. Day 2 Definition of Done

The pipeline must demonstrate:

```text
429 -> recovery/fallback
413 -> chunking
bad JSON -> validation failure/retry
stale record -> rejected
duplicate -> blocked
messy name -> canonicalized
```

---

# 48. Day 3 — Scale, Evidence, Export, Submission

### Step 1
Scale bulk ingestion to:

```text
1,000+ startups
1,000+ products
1,000+ papers
```

Prefer going above the minimum when time and source quality allow.

### Step 2
Run fresh news/job ingestion.

### Step 3
Verify 24-hour freshness programmatically.

### Step 4
Run data quality gates.

### Step 5
Run full test suite.

### Step 6
Run benchmark.

### Step 7
Export to Google Sheets.

### Step 8
Generate architecture.pdf.

### Step 9
Finish README.

### Step 10
Perform clean-machine/containerized reproducibility test.

### Step 11
Capture evidence:

- benchmark output
- tests
- sample logs
- architecture diagram
- sample provenance record
- LLM fallback event
- freshness result
- entity mapping example

---

# 49. Final Definition of Done

The submission should satisfy:

```text
[ ] 1,000+ startups
[ ] 1,000+ products
[ ] 1,000+ research papers
[ ] GitHub stars sourced legitimately
[ ] 5 news sources
[ ] 5 job boards
[ ] 24-hour freshness gate
[ ] async crawler
[ ] Playwright path for JS sources
[ ] LLM provider abstraction
[ ] Gemini provider
[ ] Groq provider
[ ] DeepSeek provider
[ ] 413-aware semantic chunking
[ ] 429 retry + jitter
[ ] provider fallback
[ ] circuit breaker
[ ] structured validation
[ ] deterministic entity resolution
[ ] mapping log
[ ] provenance
[ ] raw content preservation
[ ] idempotency
[ ] distributed dedupe strategy
[ ] PostgreSQL
[ ] vector-store strategy
[ ] graph-store strategy
[ ] structured logging
[ ] metrics
[ ] automated tests
[ ] benchmark
[ ] Google Sheets with six tabs
[ ] README
[ ] architecture.pdf <= 3 pages
[ ] reproducible setup
```

---

# 50. 500k+ Scale Design

The system should be logically separable into:

```text
DISCOVERY
FETCH
PARSE
EXTRACT
RESOLVE
STORE
EXPORT
```

Each stage communicates through durable job boundaries.

The application code must remain stateless wherever possible.

Scaling example:

```text
               Queue
                 |
       +---------+---------+
       |         |         |
    Worker A  Worker B  Worker C
       |         |         |
       +---------+---------+
                 |
          Shared Storage
```

To increase capacity:

```text
10 workers
   ->
50 workers
   ->
100 workers
```

without rewriting source adapters.

Also account for:

- per-source rate limits
- provider limits
- database connection pooling
- object-store throughput
- queue throughput
- backpressure
- dead-letter handling

---

# 51. Backpressure

Do not let a fast crawler overwhelm downstream LLM or DB capacity.

Flow:

```text
crawl
  -> queue fills
  -> downstream queue depth observed
  -> worker concurrency reduced
  -> processing catches up
```

Expose queue depth and stage latency metrics.

---

# 52. Idempotent Pipeline Requirement

Every major stage should be safe to retry.

Examples:

```text
fetch(url)
parse(raw_document_id)
extract(raw_document_id, schema_version)
resolve(record_id)
store(record)
```

Running the same task twice should not create duplicate canonical data.

Use deterministic identity + DB uniqueness.

---

# 53. Quarantine System

Create a quarantine store/table for records that need manual or later inspection.

Examples:

```text
unresolved date
low-confidence entity match
schema validation failure
missing mandatory provenance
source content malformed
protected source unavailable
ambiguous canonical entity
```

This is preferable to either:

```text
silently discard
```

or:

```text
invent a value
```

---

# 54. Data Lineage

For every final record, be able to answer:

```text
Where did this record come from?
When was it fetched?
What exact source URL was used?
What raw document produced it?
Was an LLM used?
Which model?
Was fallback triggered?
What validation occurred?
Which canonical entity was selected?
```

Create a simple lineage chain:

```text
source URL
    |
    v
raw_document
    |
    v
extraction_result
    |
    v
validated_record
    |
    v
canonical_entity
```

---

# 55. Security / Secrets

Never commit API keys.

Use:

```text
.env
```

and `.env.example` containing variable names only.

Example:

```text
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=
GITHUB_TOKEN=
DATABASE_URL=
GOOGLE_SHEETS_CREDENTIALS=
```

Do not include real credentials in README, logs, screenshots, or Google Sheets.

---

# 56. Failure Demonstrations for the Final Review

Build a small reproducible demo command/script showing:

## Demo A — 429

Mock provider:

```text
Gemini -> 429
Groq   -> success
```

Show log:

```text
provider=gemini status=429 retry=1
provider=gemini status=429 retry_exhausted
fallback=groq
status=success
```

## Demo B — 413

Input:

```text
oversized document
```

Show:

```text
estimated_tokens=...
chunk_count=...
provider_attempt=...
final_status=success
```

## Demo C — Duplicate

Run ingestion twice:

```text
run 1 -> inserted N
run 2 -> duplicates prevented N
```

## Demo D — Freshness

Provide:

```text
23h -> accepted
26h -> rejected
```

## Demo E — Entity resolution

Show:

```text
Open AI -> OpenAI
OpenAI Inc. -> OpenAI
```

---

# 57. Quality Dashboard / CLI Summary

Create a simple summary after each run:

```text
========================================
 AI INTELLIGENCE INGESTION RUN
========================================
Run ID                 ...
Started                ...
Finished               ...

STARTUPS               1,xxx
PRODUCTS               1,xxx
RESEARCH PAPERS        1,xxx
FRESH JOBS             xxx
FRESH NEWS             xxx

HTTP SUCCESS           xx.xx%
LLM SUCCESS            xx.xx%
LLM FALLBACKS          xx
429 RECOVERIES         xx
413 RECOVERIES         xx

DUPLICATES PREVENTED   xx
QUARANTINED            xx
REJECTED               xx

FRESHNESS PASS         xx.xx%
ENTITY MATCH           xx.xx%

THROUGHPUT             xx.xx records/sec
========================================
```

All values must come from actual run metrics.

---

# 58. Submission Strategy

Final GitHub repository:

```text
README.md
architecture.pdf
src/
tests/
configs/
scripts/
docker-compose.yml
requirements.txt / pyproject.toml
```

Google Sheet:

```text
Startups
Products
Research Papers
Jobs
News
Entity Mapping Log
```

The README should link to:

- Google Sheet
- architecture PDF
- reproducible setup
- sample run
- benchmark

Do not hide important engineering decisions in code comments only.

---

# 59. What the Coding AI Must NOT Do

Do not:

1. Generate fake records just to reach 1,000 rows.
2. Fill unavailable fields with guessed values.
3. Use LLM output as source-of-truth for URLs or metrics.
4. Use synchronous crawling for the main pipeline.
5. Use an in-memory set as the only duplicate mechanism.
6. Treat Google Sheets as the primary database.
7. Use blind character truncation as the only chunking method.
8. Retry 429/413 forever.
9. Retry permanent 404-style failures without reason.
10. Launch a browser for every URL.
11. Hardcode API secrets.
12. Hardcode provider rate limits in many files.
13. Spread source-specific selectors throughout the entire codebase.
14. Claim 500k scalability without explaining queueing, stateless workers, backpressure, shared storage, and rate limits.
15. Claim metrics that were not measured.
16. Claim anti-bot bypass capabilities that were not legitimately implemented.
17. Remove raw evidence after successful extraction.
18. Export records that fail mandatory validation.
19. Let low-confidence entity resolution silently become canonical truth.
20. Overengineer the demo before the core vertical slice works.

---

# 60. Coding Sequence — Exact Order

The coding AI should execute approximately in this order:

```text
1. Initialize repository
2. Create pyproject/requirements
3. Create config system
4. Create common schemas
5. Create structured logging
6. Create async HTTP client
7. Create retry utility
8. Create rate limiter
9. Create raw storage abstraction
10. Create URL canonicalizer + hashing
11. Create PostgreSQL repository abstraction
12. Create base source adapter
13. Implement first startup source
14. Implement first product source
15. Implement research source
16. Implement GitHub client/cache
17. Run 100/100/100 vertical slice
18. Add unit tests
19. Add date parser
20. Add freshness gate
21. Add watermark/idempotency
22. Add five news sources
23. Add five job sources
24. Add LLM provider interface
25. Add Gemini
26. Add Groq
27. Add DeepSeek
28. Add orchestrator
29. Add token estimation
30. Add semantic chunker
31. Add 413 handling
32. Add 429 handling
33. Add circuit breaker
34. Add schema validation
35. Add entity normalizer
36. Add entity matching
37. Add mapping log
38. Add observability metrics
39. Add remaining bulk coverage
40. Run 1,000+ targets
41. Run quality gates
42. Run tests
43. Run benchmark
44. Export Sheets
45. Generate architecture PDF
46. Finalize README
47. Re-run from clean environment
48. Fix reproducibility issues
49. Final audit against checklist
50. Submit
```

---

# 61. Acceptance Criteria for the Coding AI

The implementation is not considered complete simply because files exist.

It is complete only when:

### Correctness

- required schemas validate
- records have source URLs
- freshness gate behaves correctly
- GitHub stars are sourced from legitimate data
- duplicate prevention works
- entity resolution is deterministic/auditable

### Reliability

- transient failures recover
- 429 is handled
- 413 is handled
- provider fallback works
- permanent failures terminate cleanly
- malformed LLM responses are rejected

### Scale

- concurrency is configurable
- workers are stateless
- storage is shared/durable
- queue abstraction exists
- 500k design is credible

### Maintainability

- source adapters are isolated
- provider adapters are isolated
- configuration is externalized
- tests cover edge cases
- logging is structured

### Evidence

- benchmark produced
- final counts measured
- quality metrics measured
- Google Sheet generated
- architecture PDF generated
- README reproducible

---

# 62. Final Mental Model

The finished system should behave like:

```text
                   INTERNET
                       |
          +------------+-------------+
          |            |             |
       STARTUPS     PRODUCTS      PAPERS
          |            |             |
          +------------+-------------+
                       |
                   DISCOVERY
                       |
                     QUEUE
                       |
              ASYNC WORKERS
                       |
           +-----------+-----------+
           |                       |
       HTTP FETCH             PLAYWRIGHT
           |                       |
           +-----------+-----------+
                       |
                  RAW STORAGE
                       |
               CONTENT CLEANING
                       |
              DATE / METADATA
                       |
                 FRESHNESS
                       |
              SEMANTIC EXTRACTION
                       |
          +------------+-------------+
          |            |             |
       GEMINI        GROQ        DEEPSEEK
          |            |             |
          +------------+-------------+
                       |
               SCHEMA VALIDATION
                       |
              ENTITY RESOLUTION
                       |
          +------------+-------------+
          |            |             |
      POSTGRES       VECTOR        GRAPH
          |
       EXPORT
          |
    GOOGLE SHEETS
```

Cross-cutting layers:

```text
PROVENANCE
IDEMPOTENCY
RETRY
RATE LIMITING
CIRCUIT BREAKING
CACHING
BACKPRESSURE
OBSERVABILITY
QUARANTINE
TESTING
```

This is the standard the coding AI should work toward.

---

# 63. Final Instruction to the Coding AI

Treat this document as the implementation contract.

Do not jump directly into generating every file.

Instead:

1. Build the smallest complete vertical slice.
2. Run it and verify real source data.
3. Add tests.
4. Generalize the successful pattern into source adapters.
5. Add reliability mechanisms.
6. Expand source coverage.
7. Benchmark.
8. Only then optimize and polish.

At every step, prefer:

```text
correct + observable + reproducible
```

over:

```text
large + impressive-looking + fragile
```

The final project should make a reviewer conclude that the engineer understands not only how to scrape data or call an LLM, but how to operate a trustworthy, fault-tolerant intelligence-ingestion system at scale.
