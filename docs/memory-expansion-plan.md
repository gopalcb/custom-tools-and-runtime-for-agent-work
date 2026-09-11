# Memory Expansion Plan

Last researched: 2026-09-10

## Goal

The agents should become better at future `projects/` work the more they run.
That means memory must help them:

- identify the right project, agent, workflow, and validation commands;
- recall architecture, conventions, and past decisions;
- avoid repeating known failed approaches;
- retrieve project-specific context without scanning the whole monorepo every
  time;
- keep old or wrong facts from contaminating new work.

The memory system should stay fact-first: events, source files, tests, ADRs,
and project docs remain stronger than generated summaries.

## Memory Types To Introduce

Start with explicit memory kinds instead of one generic "note" bucket:

- `project-profile`: project purpose, stack, entry points, run commands,
  validation commands, deployment/runtime notes.
- `architecture-fact`: stable structure, module responsibilities, data flow,
  important ownership boundaries.
- `decision`: ADR-like facts with date, rationale, alternatives, and status.
- `failure-pattern`: error signatures, root cause, verified fix, commands that
  reproduced or resolved it.
- `command-result`: important command outcomes, environment constraints, and
  known slow/flaky checks.
- `user-preference`: durable user instructions that are not already in
  `AGENTS.md`.
- `project-glossary`: local names, acronyms, domain entities, and mappings to
  source modules.
- `dependency-fact`: important framework/library versions, upgrade constraints,
  and compatibility issues.
- `integration-fact`: external APIs, auth flows, webhook contracts, service
  URLs, and source links with review dates.
- `security-constraint`: secrets handling, data boundaries, permissions, and
  unsafe operations.
- `open-question`: unresolved assumptions the agent should not silently treat
  as facts.
- `retrieval-feedback`: whether a retrieved memory was useful, ignored, or
  contradicted by later evidence.

Each memory should carry:

```yaml
schema_version: 1
id: stable-id
kind: architecture-fact
scope:
  repo: agent-monorepo
  project: projects/example
  service: api
source:
  run_id: run-...
  session_id: session-...
  events: [12, 19, 31]
  files: ["projects/example/ARCHITECTURE.md"]
content: "..."
confidence: 0.8
privacy: normal
status: active
created_at: "..."
updated_at: "..."
valid_until: null
supersedes: []
tags: []
```

## Phased Roadmap

### Phase 1: Harden Local Memory

- Add `schema_version`, `kind`, `scope`, `confidence`, `status`, and
  `source_events` fields.
- Keep deterministic extraction from `RuntimeEvent` as the baseline.
- Split candidate storage from accepted memory storage.
- Add a promotion policy: only high-signal candidates become active memory.
- Add a secret/redaction scan before promotion.
- Add tests for retrieval budget, stale memory, duplicate records, and path
  containment.
- Add a memory inspection command or report so a human can see what the agent
  believes.

### Phase 2: Project-Aware Memory

Before serious work starts in `projects/`, create a repeatable project scaffold:

```text
projects/<project-id>/
|-- AGENTS.md
|-- ARCHITECTURE.md
|-- code-map.yaml
|-- project.yaml
`-- README.md
```

`project.yaml` should declare project ID, stack, default agent, validation
commands, deployment mode, and memory namespace. The resolver can then retrieve
project memory by scope instead of searching all records equally.

### Phase 3: Consolidation

Raw run summaries should not accumulate forever. Add a consolidation command
that can be run on demand or during finalization when a threshold is crossed:

- merge repeated failure summaries into one `failure-pattern`;
- promote repeated architecture facts into `architecture-fact`;
- archive run summaries that are fully represented by higher-signal memory;
- mark contradicted memories as `superseded`;
- generate or update project `ARCHITECTURE.md` and `code-map.yaml` only when
  verified by source inspection.

Avoid a scheduler until there is a real operational need. A deterministic
maintenance command is easier to test and reason about.

### Phase 4: Hybrid Retrieval

When local lexical retrieval is no longer enough, introduce a search index.
Keep JSON files as the durable source of truth and build the index from them.

Recommended retrieval pipeline:

1. Determine scope from user request, current path, resolver output, and
   project registry.
2. Retrieve candidates with lexical search for exact filenames, commands,
   error strings, and IDs.
3. Retrieve candidates with vector search for semantic architecture and prior
   work.
4. Filter by `project`, `service`, `kind`, `status`, `privacy`, and validity.
5. Merge results with reciprocal-rank or normalized score fusion.
6. Re-rank by recency, confidence, source quality, and task fit.
7. Compress to a strict token budget before prompt injection.

AWS OpenSearch is a good fit for the first production-grade store because
OpenSearch Serverless vector collections support k-NN, full-text search,
filters, aggregations, metadata fields, and vectors up to 16,000 dimensions.
AWS documents hybrid search with keyword plus semantic search, normalization,
and a hybrid query. That is useful for agent memory because exact strings and
semantic similarity are both first-class.

Suggested OpenSearch index shape:

```json
{
  "memory_id": "string",
  "repo": "keyword",
  "project": "keyword",
  "service": "keyword",
  "agent_id": "keyword",
  "kind": "keyword",
  "status": "keyword",
  "privacy": "keyword",
  "confidence": "float",
  "created_at": "date",
  "updated_at": "date",
  "valid_until": "date",
  "tags": "keyword",
  "source_files": "keyword",
  "content": "text",
  "embedding": "knn_vector"
}
```

Operational cautions:

- Serverless still needs IAM, data access policies, collection lifecycle, and
  cost monitoring.
- AWS notes read-after-write and newly-created pipeline/index latency, so the
  local JSON store should remain the immediate source after a run.
- Embedding model changes require re-indexing or dual-index compatibility.
- Hybrid search quality needs evaluation queries; otherwise it can look
  sophisticated while returning worse context.

### Phase 5: Performance Feedback

Add metrics that tell whether memory helps:

- retrieval hit count and injected token count per run;
- memory records read and filtered per run;
- top retrieved memory IDs and scores;
- whether the final answer or code changes referenced retrieved memory;
- validation success rate when memory was used;
- stale or contradicted memory incidents;
- time spent in retrieval and indexing.

Use these to tune:

- per-task token budgets;
- which memory kinds are retrieved by default;
- confidence decay;
- when to consolidate;
- whether embeddings are worth the extra infrastructure.

## Research Notes

- Codex project instructions are loaded from `AGENTS.md`, with root-to-current
  directory layering and size limits:
  https://learn.chatgpt.com/docs/agent-configuration/agents-md
- OpenAI embeddings are documented as useful for search, clustering,
  recommendations, anomaly detection, and classification:
  https://developers.openai.com/api/docs/models/text-embedding-3-small
- OpenAI embeddings API limits include 8,192 tokens per input and 300,000
  summed tokens per request:
  https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create
- OpenAI vector store search provides query, filters, ranking options, query
  rewrite, and result scores:
  https://developers.openai.com/api/reference/python/resources/vector_stores/methods/search
- Amazon OpenSearch Serverless vector search collections support vector search,
  full-text search, filters, metadata fields, and 16,000 dimensions:
  https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html
- Amazon OpenSearch Serverless hybrid search combines keyword and semantic
  search with normalization and hybrid queries:
  https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-configure-neural-search.html
