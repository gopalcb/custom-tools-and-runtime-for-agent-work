# How Memory Candidates Work

Last researched: 2026-09-10

Note: this file keeps the requested filename spelling, `candiates`, so links to
the user-requested path remain stable.

## Current Approach

Memory candidates are deterministic run artifacts derived from the runtime event
stream. They are not created by asking a model to summarize the run.

The source record for a run is:

```text
.agent-state/logs/<session-id>/<run-id>/events.jsonl
```

During finalization, `agent-runtime/agent-monorepo/post_completion.py` loads the
persisted events and writes:

```text
run.json
summary.md
metrics.json
artifacts.json
memory_candidates.json
```

When memory extraction is enabled in `project-registry.yaml`,
`MemoryService.prepare_candidates()` builds candidate records from the same
events and stores retrievable JSON records under:

```text
.agent-state/cache/memory/records/<session-id>/<run-id>/*.json
```

Today the candidate kinds are:

- `run-summary`: request, status, resolved agent, workflow selection, changed
  files, artifacts, failures, and final message when available.
- `failure-summary`: unique failed step, tool, background, and error messages.
- `change-summary`: changed files and created artifacts.

The runtime can also store user strategy memory from post-work feedback when
`memory.strategy_feedback.enabled` is true. This happens after validation and
before finalization in the default workflow. The feedback GUI writes a
run-scoped `strategy-feedback.json` artifact; the `strategy-memory-analyzer`
agent proposes memory actions; deterministic memory code validates and writes
active strategy records under:

```text
.agent-state/cache/memory/records/strategy/*.json
```

Strategy records use `kind: user-work-strategy` or a closely related
preference/feedback kind. Updates preserve older records by marking them
`superseded` instead of deleting them.

Retrieval is local and lexical. `MemoryService.retrieve_context()` loads stored
records, ranks them with `MemoryRetriever`, and injects the top hits into the
next Codex developer instructions under `Retrieved project memory`.

Important current properties:

- Candidate generation has no model call and no embedding call.
- Records are file-backed JSON, so they are inspectable and portable.
- Retrieval is opt-in by policy and bounded to five hits by default.
- Each retrieved hit is truncated to 2,400 characters before prompt injection.
- Strategy-feedback analysis uses a focused analyzer turn only when the user
  submits the feedback form; cancel and headless-unavailable states store no
  durable strategy memory.
- The current implementation is useful for remembering prior run failures and
  recent project-specific facts, but it is not yet semantic long-term memory.

## Token Consumption

Current memory candidate generation consumes zero model tokens. It parses
already persisted `RuntimeEvent` objects and writes local JSON.

Current retrieval consumes prompt tokens only when retrieved memory is injected
into a Codex turn. The default budget is approximately:

```text
5 hits * 2,400 chars/hit ~= 12,000 chars
12,000 chars / ~4 chars per token ~= 3,000 tokens
```

There is small overhead for headings, paths, and scores. A no-hit run adds only
the short fallback sentence.

The prompt-token cost matters more than the local storage cost. If the runtime
injects roughly 3,000 memory tokens into ten runs per day, that is about 30,000
extra prompt tokens per day or 900,000 per month. The exact dollar impact
depends on the Codex model and pricing in use, but the operational impact is
also context pressure: stale or irrelevant memory can crowd out source context
and user instructions.

If semantic retrieval is added later, embedding cost is separate from prompt
cost. OpenAI currently documents `text-embedding-3-small` at $0.02 per 1M input
tokens and `text-embedding-3-large` at $0.13 per 1M input tokens. The embeddings
API also documents an 8,192-token per-input limit and a 300,000-token summed
limit per request. Those numbers make embedding local memory records cheap
relative to repeated prompt injection, but pricing and limits should be
rechecked at implementation time.

## Drawbacks

The current approach is intentionally simple. Its main drawbacks are:

- Lexical retrieval misses semantically related facts when the same terms do
  not appear in the query and record.
- Lexical retrieval can over-rank repeated words, stale failure text, or
  low-value run summaries.
- There is no human or automated approval gate before a candidate becomes
  retrievable memory.
- There is no conflict resolution when a newer memory supersedes an older one.
- There is no expiration policy, stale-memory review, or confidence decay.
- There is no privacy classification, redaction pass, or secret scanner before
  storage.
- Memory scope is mostly metadata today; future `projects/` work needs stronger
  per-project, per-service, and per-agent boundaries.
- Failed runs are useful to remember, but they can pollute memory if the failure
  was caused by a temporary environment state.
- Retrieval quality is not measured with evaluation queries, so regressions can
  slip in quietly.
- Prompt injection is capped per hit, but there is no global token-aware budget
  tied to the active model context window.

## Improvements

Near-term improvements that fit the current architecture:

- Add a `schema_version` to memory records.
- Store `source_events` with event sequence numbers so every memory can be
  traced back to facts.
- Add `scope` fields: `repo`, `project`, `service`, `agent`, `workflow`.
- Add `kind` fields beyond run summaries: `architecture`, `decision`,
  `failure-pattern`, `command-result`, `user-preference`, `project-glossary`,
  `dependency-fact`, `integration-fact`, and `open-question`.
- Add `confidence`, `valid_from`, `valid_until`, `supersedes`, and `privacy`
  metadata.
- Add a redaction pass for secrets and local-only paths before records become
  retrievable.
- Add a memory quality test suite with fixed queries and expected top records.
- Add a retrieval token budget, for example 1,000 tokens for ordinary tasks and
  3,000 tokens for architecture/debugging tasks.
- Add deduplication by stable subject, kind, and normalized content hash.
- Prefer high-signal memory over full run summaries when both match.

Medium-term improvements:

- Add an explicit promotion step from "candidate" to "accepted memory".
- Consolidate repeated run summaries into durable project knowledge.
- Decay or archive records that are not retrieved for a long time.
- Record when a retrieved memory influenced a successful run.
- Add conflict checks: newer memory should be able to replace older records
  rather than merely coexist with them.

Semantic retrieval improvements:

- Keep the local JSON memory store as the durable source of truth.
- Add embeddings as an index, not as the only copy of memory.
- Use hybrid search when memory grows beyond lexical retrieval: keyword search
  catches exact file names, commands, IDs, and error strings; vector search
  catches semantic similarity.
- Re-rank retrieved results with metadata filters and a token budget before
  prompt injection.

AWS OpenSearch is a reasonable future store because Amazon OpenSearch
Serverless supports vector search collections, k-NN vector fields, metadata
fields, full-text search, filtering, and dimensions up to 16,000. AWS also
documents hybrid search for Serverless by combining keyword and semantic search
with a normalization search pipeline and hybrid query. That maps well to agent
memory because exact project identifiers and semantic architecture facts both
matter.

## Research Notes

- Codex reads `AGENTS.md` before work and layers project instructions from the
  repository root toward the working directory:
  https://learn.chatgpt.com/docs/agent-configuration/agents-md
- OpenAI embeddings model pricing and embedding use cases:
  https://developers.openai.com/api/docs/models/text-embedding-3-small
- OpenAI embeddings API input limits:
  https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create
- OpenAI vector store search supports query, filters, ranking options, query
  rewrite, and up to 50 search results:
  https://developers.openai.com/api/reference/python/resources/vector_stores/methods/search
- Amazon OpenSearch Service vector search overview:
  https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vector-search.html
- Amazon OpenSearch Serverless vector search collections:
  https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html
- Amazon OpenSearch Serverless neural and hybrid search:
  https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-configure-neural-search.html
- OpenSearch hybrid search:
  https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
