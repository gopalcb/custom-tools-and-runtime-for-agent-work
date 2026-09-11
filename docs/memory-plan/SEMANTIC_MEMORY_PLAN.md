# Agent Semantic Memory on AWS OpenSearch

**Status:** Implementation plan  
**Scope:** Agent monorepo semantic/episodic/procedural memory  
**Root folder:** `semantic-memory/`  
**Primary vector store:** Amazon OpenSearch Serverless, NextGen Vector Search  
**Embedding model:** Amazon Titan Text Embeddings V2  
**Primary language:** Python  
**Design goal:** High-value memory with low retrieval noise, low prompt-token overhead, clear provenance, and safe evolution over time.

---

## 1. Executive summary

The memory system should **not** be a vectorized copy of agent conversations, logs, source code, or every tool output. That creates a large index but a poor memory system: retrieval becomes noisy, stale facts compete with current facts, duplicate memories multiply, and agents spend tokens reading irrelevant context.

The recommended architecture is instead:

1. Keep raw agent interaction logs as **evidence**, outside the semantic-memory vector index.
2. Run a selective **memory extraction + consolidation** step after meaningful agent work.
3. Store only compact, self-contained, future-useful memory records in OpenSearch.
4. Keep memory records typed: `semantic`, `episodic`, `reflection`, and later `procedural_pointer`.
5. Retrieve with hard metadata filters first, then semantic + lexical retrieval, then deduplicate/rerank.
6. Inject only a very small number of high-confidence memories into the agent context.
7. Preserve provenance and supersession so a memory can be traced to the run, file, commit, or decision that produced it.
8. Treat the live repository and current project instructions as more authoritative than memory.
9. Evaluate memory as a subsystem using retrieval accuracy, conflict resolution, stale-memory rate, token cost, and downstream task success.

This follows the direction of modern agent-memory work: modular memory, selective consolidation, episodic reflection, hierarchical context, and explicit evaluation of retrieval/conflict/forgetting rather than simply increasing context length. [R1][R2][R3][R4][R5]

---

# 2. Philosophy

## 2.1 Memory is a distilled working asset, not an archive

An archive answers:

> “What happened?”

Agent memory should answer:

> “What previously learned information is useful for this task right now?”

Those are different systems.

Use the existing agent logs/S3 work logs as the archive. OpenSearch memory should contain only distilled information that has a reasonable chance of improving a future task.

A useful memory record is usually one of these:

- a durable fact about the project;
- an architectural constraint;
- a decision and its rationale;
- a known successful approach;
- a known failed approach and why it failed;
- a completed troubleshooting episode;
- a repeated pattern learned across episodes;
- a pointer to an authoritative procedure or skill.

A poor memory record is usually one of these:

- an entire prompt;
- an entire assistant answer;
- a large raw code block;
- a full git diff;
- console noise;
- a one-time intermediate hypothesis;
- a transient status message;
- repeated restatements of the same fact;
- an unverified inference;
- data already cheaply obtainable from the live repository.

The write path is therefore more important than the vector database.

---

## 2.2 Prefer precision over recall when injecting context

For an agent, an irrelevant retrieved memory is not neutral. It consumes tokens and can influence reasoning in the wrong direction.

Therefore:

- retrieve broadly internally;
- inject narrowly into the model;
- return no long-term memory when evidence is weak;
- never fill a fixed quota merely because `top_k=8` was configured.

The system should be comfortable returning zero memories.

---

## 2.3 Memory has types because different information has different persistence rules

Do not apply one lifecycle policy to everything.

### Working memory

Current task, recent messages, current tool state, current plan.

- lifetime: current run/session;
- location: agent runtime/context;
- not stored in OpenSearch as long-term memory by default.

### Semantic memory

Durable facts and contextual knowledge.

Examples:

- “The secure Angular host must wait for `/user` before rendering protected content.”
- “The project keeps agent definitions under `monorepo/agents/`.”
- “This repository prefers validation outside core logical functions.”

AWS AgentCore’s semantic memory strategy similarly focuses on extracting factual information and contextual knowledge, then consolidating it into long-term records. [R6]

### Episodic memory

A compact record of a meaningful completed experience.

Examples:

- a failed deployment and the change that fixed it;
- an Angular routing issue, attempted approaches, final fix, and outcome;
- a tool workflow that consistently solved a class of tasks.

AWS AgentCore’s episodic strategy models episodes using situation/intent/actions/outcomes and can create higher-level reflections across episodes. [R7]

### Reflective memory

A generalized lesson supported by multiple episodes.

Example:

> “When secure-path rewrites are performed both in Kong and Angular routing, duplicate `/secure` segments are a recurring failure mode. Normalize at one boundary and verify the resulting model path.”

Reflections should require more evidence than ordinary semantic facts.

### Procedural memory

How the agent should perform recurring work: skills, workflows, runbooks, code-quality rules, architecture rules.

Procedural knowledge should normally live in **version-controlled files**, not be silently rewritten inside a vector database.

OpenSearch may index a compact pointer/description so the resolver can discover the right skill, but Git remains the source of truth.

---

## 2.4 Current truth outranks remembered truth

Authority order for coding agents:

1. current system/developer/agent instructions;
2. current user request;
3. live repository files and live environment state;
4. current authoritative architecture/configuration documents;
5. validated long-term memory;
6. historical episodic memory;
7. raw archived logs.

If memory says a function is in `a.py` but the current repository says it moved to `b.py`, the repository wins.

This rule is critical for preventing stale code memories from creating regressions.

---

# 3. Research basis and design implications

## 3.1 Modular memory

CoALA proposes modular memory for language agents rather than treating context as one undifferentiated buffer. [R1]

**Implementation implication:** keep memory types explicit and let retrieval policies differ by type.

## 3.2 Hierarchical memory instead of unlimited prompt history

MemGPT demonstrated an OS-inspired hierarchy in which information is moved between fast limited context and larger external memory. [R2]

**Implementation implication:** the LLM prompt is a cache, not the database. Retrieve only the small subset needed for the current task.

## 3.3 Observation → retrieval → reflection

Generative Agents used stored experiences plus dynamically retrieved memories and higher-level reflection. [R3]

**Implementation implication:** Phase 2 adds reflection over repeated episodes, rather than endlessly accumulating raw episodes.

## 3.4 Extraction and consolidation matter

Mem0 describes a production-oriented pattern in which new interactions are selectively distilled and compared with related existing memories before deciding how memory should change. Its published work also shows substantial token/latency benefits versus full-context approaches. [R4]

**Implementation implication:** candidate memories must be checked against existing memories before embedding/indexing.

## 3.5 Memory needs its own evaluation

MemoryAgentBench identifies retrieval, test-time learning, long-range understanding, and selective forgetting/conflict handling as distinct competencies. [R5]

**Implementation implication:** do not judge this system only by whether search returns “something.” Build a dedicated eval set and measure retrieval correctness and conflict handling.

## 3.6 AWS managed-memory concepts validate the same separation

Amazon Bedrock AgentCore Memory now exposes short-term memory and long-term strategies including semantic, summaries/preferences, and episodic memory. Episodic memory includes extraction, consolidation, and reflection. [R7][R8]

**Implementation implication:** use these concepts as architecture references, but retain the self-managed OpenSearch pipeline so the monorepo controls schema, filtering, provenance, conflict rules, and cost.

---

# 4. Why use OpenSearch directly

Amazon Bedrock Knowledge Bases are excellent for document RAG, and AWS increasingly provides managed knowledge-base/agentic-retrieval capabilities. [R9][R10]

However, long-term **agent memory** has requirements beyond document retrieval:

- frequent small writes;
- update/supersession semantics;
- typed memories;
- user/repository/agent scoping;
- different decay rules by type;
- provenance back to a run/commit/file;
- conflict handling;
- evaluation of what is safe to inject;
- future code-aware invalidation.

For this project, direct OpenSearch is the better primary store because it preserves control while still using AWS-native vector infrastructure.

Bedrock remains useful for:

- embeddings;
- optional extraction model calls;
- optional reranking in Phase 2.

---

# 5. AWS architecture

## 5.1 Phase 1 infrastructure

```text
Agent / Resolver
      |
      | retrieve(task context)
      v
semantic-memory Python package
      |
      +--> Bedrock Titan Text Embeddings V2
      |
      +--> OpenSearch Serverless NextGen Vector collection
      |
      +--> raw source/event URI points to existing S3 agent logs

Post-completion hook
      |
      v
memory extraction -> consolidation -> embedding -> OpenSearch write
```

### AWS services

- **OpenSearch Serverless NextGen – Vector Search collection**
- **Amazon Bedrock – Titan Text Embeddings V2**
- **AWS KMS** through OpenSearch Serverless encryption
- **IAM + OpenSearch data access policy**
- existing **S3 agent logs** as provenance/evidence

Do not add Lambda, SQS, DynamoDB, Neptune, or a standalone API service in Phase 1 unless another existing subsystem requires them.

That keeps the first implementation understandable and easy to debug.

## 5.2 Why OpenSearch Serverless NextGen

AWS currently supports NextGen Vector Search collections. NextGen collection groups can scale search/indexing capacity to zero after an idle period, making them attractive for development and intermittent agent workloads. [R11][R12]

Use **Standard Create**, not an overly permissive Express Create, for production so network access, KMS choice, and data access are explicit.

### Recommended environments

```text
dev:  semantic-memory-dev
prod: semantic-memory-prod
```

Do not create a collection per agent. Use metadata scoping inside one collection per environment unless scale or security requirements later justify separation.

---

# 6. Embeddings

## 6.1 Model

Use:

```text
amazon.titan-embed-text-v2:0
```

Titan Text Embeddings V2 supports 1024, 512, or 256 dimensions and normalization. AWS recommends logical segmentation for retrieval workloads. [R13][R14]

### Phase 1 default

```yaml
embedding:
  provider: bedrock
  model_id: amazon.titan-embed-text-v2:0
  dimensions: 512
  normalize: true
```

Why start at 512:

- half the vector dimensions of 1024;
- lower vector storage and transfer overhead;
- agent memories are short distilled units rather than large documents;
- retrieval quality can be measured before paying for larger vectors.

This is a project recommendation, not an assumption that 512 is universally superior. The evaluation harness must compare 512 vs 1024 before a production-quality lock-in if retrieval quality is insufficient.

## 6.2 Embed the memory, not the metadata dump

Good embedding input:

```text
Angular secure host: protected routes must not render until the /user authentication call completes. Public-host behavior should remain unchanged.
```

Bad embedding input:

```text
{"agent_id":"fullstack-dev","session_id":"abc","timestamp":"...","file":"...", ... 70 metadata fields ...}
```

Metadata should be filterable fields, not mixed into semantic content unless it changes meaning.

## 6.3 Embedding versioning

Every memory must include:

```json
{
  "embedding_model": "amazon.titan-embed-text-v2:0",
  "embedding_dimensions": 512,
  "embedding_version": "titan-v2-512-v1"
}
```

Never silently change embedding models in place.

A future migration should create a new index or dual-write embeddings until backfill is complete.

---

# 7. What should enter semantic memory

## 7.1 Strong candidates

Store when information is:

- likely useful in a future run;
- reasonably stable;
- self-contained;
- verified by the task outcome, current repository, user decision, or authoritative source;
- not cheaply reconstructed every time;
- specific enough to guide future work.

Examples:

### Architecture fact

```text
The agent monorepo uses a single resolver entry point to load agent instructions, mapped skills, and workflow configuration.
```

### Constraint

```text
For secure AEM pages, the public site must continue to coexist after migration; secure-only routing behavior must not affect public routes.
```

### Decision

```text
Agent procedural rules remain version-controlled as skills/instruction files. Semantic memory may index pointers but does not replace those files.
```

### Failure knowledge

```text
Adding /secure without first checking whether it already exists produced duplicate secure paths in Kong rewrites; normalize the path before insertion.
```

## 7.2 Usually reject

Do not store by default:

- greetings;
- repeated user wording;
- speculative assistant statements;
- “I will now…” workflow narration;
- full command output;
- full stack traces after the root cause is known;
- raw HTML pages;
- full source files;
- source code that can be retrieved from Git;
- temporary local file paths with no future value;
- one-off timestamps;
- token usage logs;
- API credentials, cookies, tokens, passwords, secrets;
- personally sensitive information not required for the agent’s job.

## 7.3 Do not make code memory a substitute for code search

For coding agents, OpenSearch memory should remember **why** and **what was learned**, not duplicate the repository.

Store:

```text
AEMDataResolver intentionally returns false on SSR for secure-host pages to defer secure rendering to CSR after authentication.
```

Do not store:

```text
<600 lines of resolver.ts>
```

The agent should open the current file when exact implementation details matter.

---

# 8. Memory record model

Use one OpenSearch index in Phase 1:

```text
agent-memory-v1
```

Keep all long-term memory types together and filter by `memory_type`.

## 8.1 Logical schema

```json
{
  "memory_id": "mem_01...",
  "memory_type": "semantic",
  "subtype": "architecture_fact",
  "content": "...",
  "embedding": [0.1, 0.2],

  "project_id": "miscellaneous",
  "repo_id": "agent-monorepo",
  "workspace_id": "default",
  "agent_id": "fullstack-dev",
  "scope": "repo",

  "entities": ["Angular", "AEMDataResolver", "secure-host"],
  "tags": ["angular", "ssr", "auth"],

  "status": "active",
  "confidence": 0.94,
  "importance": 0.84,
  "evidence_count": 1,

  "created_at": "2026-09-10T20:00:00Z",
  "updated_at": "2026-09-10T20:00:00Z",
  "valid_from": "2026-09-10T20:00:00Z",
  "valid_to": null,

  "supersedes_id": null,
  "content_hash": "sha256:...",

  "source_event_id": "run_...",
  "source_uri": "s3://.../final-output.md",
  "source_commit": "abc123",
  "source_file": "src/app/.../resolver.ts",
  "source_symbol": "AEMDataResolver.resolve",
  "source_hash": "sha256:...",

  "embedding_model": "amazon.titan-embed-text-v2:0",
  "embedding_dimensions": 512,
  "embedding_version": "titan-v2-512-v1"
}
```

## 8.2 Required fields

Minimum required:

```text
memory_id
memory_type
content
project_id
scope
status
confidence
importance
created_at
updated_at
content_hash
source_event_id or source_uri
embedding_version
```

## 8.3 Scope

Use an explicit scope hierarchy:

```text
global
project
repo
agent
user
session
```

A memory can be attached to one primary scope plus metadata filters.

Default technical-agent memories should be `project` or `repo` scoped.

Avoid `global` unless the fact is intentionally shared across repositories.

---

# 9. OpenSearch mapping

A representative index mapping:

```json
{
  "settings": {
    "index.knn": true
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "memory_id": { "type": "keyword" },
      "memory_type": { "type": "keyword" },
      "subtype": { "type": "keyword" },
      "content": { "type": "text" },
      "embedding": {
        "type": "knn_vector",
        "dimension": 512,
        "space_type": "cosinesimil"
      },
      "project_id": { "type": "keyword" },
      "repo_id": { "type": "keyword" },
      "workspace_id": { "type": "keyword" },
      "agent_id": { "type": "keyword" },
      "scope": { "type": "keyword" },
      "entities": { "type": "keyword" },
      "tags": { "type": "keyword" },
      "status": { "type": "keyword" },
      "confidence": { "type": "float" },
      "importance": { "type": "float" },
      "evidence_count": { "type": "integer" },
      "created_at": { "type": "date" },
      "updated_at": { "type": "date" },
      "valid_from": { "type": "date" },
      "valid_to": { "type": "date" },
      "supersedes_id": { "type": "keyword" },
      "content_hash": { "type": "keyword" },
      "source_event_id": { "type": "keyword" },
      "source_uri": { "type": "keyword", "index": false },
      "source_commit": { "type": "keyword" },
      "source_file": { "type": "keyword" },
      "source_symbol": { "type": "keyword" },
      "source_hash": { "type": "keyword" },
      "embedding_model": { "type": "keyword" },
      "embedding_dimensions": { "type": "integer" },
      "embedding_version": { "type": "keyword" }
    }
  }
}
```

AWS OpenSearch supports `knn_vector`, vector dimensions, distance/space configuration, and filtered vector search. [R15][R16]

For NextGen collections, keep the mapping simple and avoid coupling the application to engine-specific tuning that NextGen manages for you. AWS notes that engine configuration differs between NextGen and Classic collections. [R11]

---

# 10. Phase 1 — Minimal high-quality semantic memory

Phase 1 should solve one problem extremely well:

> Retrieve a small set of reliable, useful past project knowledge before an agent starts a task.

Do not begin with graph memory, autonomous reflection, multi-agent shared learning, or complex background jobs.

## 10.1 Phase 1 capabilities

Implement:

- typed semantic memory;
- lightweight completed-task episodic memory;
- selective extraction;
- exact deduplication;
- semantic near-duplicate detection;
- supersession rather than destructive overwrite;
- OpenSearch vector search;
- lexical/BM25 search;
- application-side reciprocal-rank fusion;
- metadata filters;
- strict prompt budget;
- provenance;
- memory feedback/logging;
- custom evaluation suite.

Do not implement yet:

- graph database;
- auto-generated procedural skills;
- autonomous reflection jobs;
- cross-repository global learning;
- per-memory LLM scoring during every retrieval;
- complex service mesh;
- real-time event streaming.

---

# 11. Phase 1 folder structure

Everything belongs under root-level `semantic-memory/`.

```text
semantic-memory/
├── SEMANTIC_MEMORY_PLAN.md
├── config/
│   └── memory.yaml
├── src/
│   └── semantic_memory/
│       ├── __init__.py
│       ├── models.py
│       ├── store.py
│       ├── extractor.py
│       └── service.py
├── infra/
│   └── template.yaml
├── scripts/
│   ├── bootstrap.py
│   └── evaluate.py
└── tests/
    ├── fixtures/
    │   └── memory_eval.jsonl
    ├── test_extractor.py
    ├── test_store.py
    └── test_retrieval.py
```

This intentionally avoids many tiny modules.

## File responsibilities

### `models.py`

All request/response/data models and validation.

Contains:

- `MemoryType`
- `MemoryCandidate`
- `MemoryRecord`
- `MemoryQuery`
- `RetrievedMemory`
- `MemoryContext`
- `ConsolidationDecision`

Use Pydantic if already acceptable in the monorepo; otherwise dataclasses plus explicit validators.

### `store.py`

All AWS I/O:

- Bedrock embeddings;
- OpenSearch signed client;
- index/create/upsert/get/search operations;
- vector search;
- lexical search;
- bulk operations.

Do not scatter AWS calls throughout extraction/retrieval logic.

### `extractor.py`

Pure memory intelligence:

- candidate extraction prompt;
- deterministic eligibility checks;
- secret/noise filters;
- consolidation decision;
- memory normalization.

### `service.py`

Public facade used by the monorepo:

```python
memory.remember(...)
memory.retrieve(...)
memory.render_context(...)
memory.feedback(...)
```

It orchestrates the other modules but should not implement low-level AWS operations.

### `infra/template.yaml`

CloudFormation for:

- OpenSearch Serverless NextGen vector collection/group;
- KMS configuration if a customer-managed key is selected;
- network policy;
- data access policy;
- least-privilege IAM role/policy outputs.

### `bootstrap.py`

Developer convenience:

- validate configuration;
- confirm AWS identity/region;
- verify collection endpoint;
- create index mapping if absent;
- run one embedding + write + retrieval smoke test.

### `evaluate.py`

Runs the memory-specific evaluation dataset and emits:

- Precision@K;
- Recall@K;
- MRR;
- stale-memory rate;
- contradiction rate;
- average injected tokens;
- p50/p95 retrieval latency;
- empty-result correctness.

---

# 12. Configuration

Example `config/memory.yaml`:

```yaml
memory:
  enabled: true
  index_name: agent-memory-v1

  embedding:
    provider: bedrock
    model_id: amazon.titan-embed-text-v2:0
    dimensions: 512
    normalize: true
    version: titan-v2-512-v1

  write:
    min_confidence: 0.75
    min_importance: 0.55
    max_candidates_per_run: 8
    allow_types:
      - semantic
      - episodic

  retrieve:
    vector_candidates: 20
    lexical_candidates: 20
    fused_candidates: 12
    max_memories: 8
    max_context_tokens: 2500
    rrf_k: 60

  scope:
    require_project_id: true
    default_scope: repo

  security:
    reject_secret_patterns: true
    reject_raw_credentials: true

aws:
  region: ${AWS_REGION}
  opensearch_endpoint: ${SEMANTIC_MEMORY_OPENSEARCH_ENDPOINT}
```

Important: the confidence/importance values above are **initial engineering defaults**. They should be tuned against your evaluation dataset, not treated as universal truths.

---

# 13. Phase 1 write pipeline

```text
completed agent run
      |
      v
build compact run input
      |
      v
candidate extraction
      |
      v
eligibility gate
      |
      v
hash dedupe
      |
      v
retrieve similar existing memories
      |
      v
consolidation decision
      |
      +--> NOOP
      +--> ADD
      +--> UPDATE metadata/evidence
      +--> SUPERSEDE old + ADD new
      |
      v
embed accepted content
      |
      v
OpenSearch write
```

## 13.1 Input to extraction

Do not send the entire raw transcript unless required.

Use a compact `MemoryWriteInput`:

```python
class MemoryWriteInput(BaseModel):
    project_id: str
    repo_id: str | None
    agent_id: str
    session_id: str
    task: str
    final_summary: str
    outcome: Literal["success", "partial", "failed"]
    decisions: list[str] = []
    errors: list[str] = []
    resolved_errors: list[str] = []
    changed_files: list[str] = []
    changed_symbols: list[str] = []
    source_event_id: str
    source_uri: str | None = None
    source_commit: str | None = None
```

If the post-completion logging system already creates structured run metadata, use it directly.

## 13.2 Extraction prompt

The extraction prompt should be conservative.

```text
You extract long-term memory for a software-engineering agent.

Create a memory candidate only when the information is:
- useful for a future task,
- supported by this completed run,
- self-contained,
- specific,
- not merely a restatement of the task,
- not easily recovered from current source code,
- not a credential/secret,
- not an unverified guess.

Prefer:
- architecture constraints,
- durable decisions,
- confirmed root causes,
- successful fixes,
- important failed approaches,
- stable project conventions.

Reject:
- raw logs,
- complete code blocks,
- temporary status,
- conversational filler,
- speculative ideas.

Return no candidate when nothing deserves long-term memory.
```

Expected structured output:

```json
{
  "candidates": [
    {
      "memory_type": "semantic",
      "subtype": "failure_resolution",
      "content": "...",
      "confidence": 0.92,
      "importance": 0.82,
      "entities": ["Kong", "secure path"],
      "tags": ["routing", "rewrite"]
    }
  ]
}
```

## 13.3 Deterministic eligibility gate

Do not trust the extraction model alone.

Reject when:

- content is blank or very short and context-free;
- candidate exceeds configured length;
- content contains recognized credentials/secrets;
- confidence below threshold;
- importance below threshold;
- memory type is not allowlisted;
- it matches a raw-log pattern;
- it is a duplicate content hash;
- it contains only file content without a lesson/decision.

The gate should be simple and explainable.

## 13.4 Consolidation

Before ADD, retrieve the five most similar active memories within the same project/repo and compatible type.

Then decide one of:

```text
ADD         genuinely new information
UPDATE      same fact; strengthen metadata/evidence/source
SUPERSEDE   old fact is no longer true; preserve old historical record
NOOP        duplicate, weaker, or irrelevant
```

Prefer `SUPERSEDE` over hard delete.

Hard deletion should be reserved for:

- explicit purge;
- security/privacy removal;
- clearly corrupted records.

### Why preserve superseded memory?

A coding agent sometimes needs historical context:

> “Why was this changed?”

Deleting old memory destroys that explanation.

## 13.5 Embed only after acceptance

Do not pay to embed candidates that will be rejected as duplicates/noise.

Order:

```text
extract -> gate -> consolidate -> embed -> index
```

not:

```text
embed everything -> decide later
```

---

# 14. Phase 1 retrieval pipeline

```text
current task
   |
   v
build compact memory query
   |
   v
resolve hard scope filters
   |
   +--> vector search top 20
   |
   +--> lexical/BM25 top 20
   |
   v
RRF merge
   |
   v
remove stale/inactive/duplicates
   |
   v
relevance + authority rules
   |
   v
context budget selection
   |
   v
0..8 memories returned
```

## 14.1 Query input

```python
class MemoryQuery(BaseModel):
    text: str
    project_id: str
    repo_id: str | None = None
    agent_id: str | None = None
    allowed_types: list[MemoryType] = [
        MemoryType.SEMANTIC,
        MemoryType.EPISODIC,
    ]
    entities: list[str] = []
    current_files: list[str] = []
    token_budget: int = 2500
```

Query text should be a compact task representation, not blindly the full chat history.

Good:

```text
Fix Kong rewrite for secure AEM model paths. Avoid duplicate /secure segments and preserve en/fr language handling.
```

## 14.2 Hard filters before ranking

Use metadata filters to reduce noise before semantic ranking.

Typical filters:

```text
project_id == current project
status == active
memory_type in requested types
repo_id == current repo OR scope == project/global
```

Optionally:

```text
agent_id == current agent OR memory is repo/project shared
```

OpenSearch supports filtered k-NN/vector search. [R16]

## 14.3 Hybrid retrieval

Use both:

- vector similarity for semantic meaning;
- BM25/lexical retrieval for exact symbols, error codes, filenames, endpoints, API names.

Examples where lexical search matters:

```text
AEMDataResolver
cloudformation:DescribeStacks
/content/ca-aem/ca
ERR_HTTP_HEADERS_SENT
```

Pure vector search may underweight exact technical tokens.

## 14.4 Reciprocal rank fusion

Phase 1 should merge vector and BM25 results in application code using RRF.

OpenSearch itself supports hybrid search and RRF/search-pipeline patterns, but application-side fusion is easier to inspect and tune in the first implementation. OpenSearch describes RRF as useful when lexical and semantic score scales are not directly comparable. [R17][R18]

Pseudo-code:

```python
def reciprocal_rank_fusion(result_lists, k=60):
    scores = {}
    documents = {}

    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            memory_id = item.memory_id
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (k + rank)
            documents[memory_id] = item

    return sorted(
        documents.values(),
        key=lambda item: scores[item.memory_id],
        reverse=True,
    )
```

## 14.5 Do not use a copied universal vector threshold

A cosine similarity threshold that works for one embedding distribution may fail for another.

Instead:

1. create labeled positive/negative retrieval cases;
2. record similarity/rank distributions;
3. choose a threshold from actual precision/recall tradeoffs;
4. allow no-memory results.

## 14.6 Deduplicate before prompt injection

If results say essentially the same thing, only inject the strongest/latest active version.

Dedup rules:

- exact `content_hash`;
- `supersedes_id` chain;
- same `source_symbol` + highly similar content;
- semantic near-duplicate clustering.

## 14.7 Context budget

Initial target:

```text
maximum long-term memory context: ~2,500 tokens
maximum memories: 8
```

Prefer 3 excellent memories over 8 weak ones.

A typical injected context should be much smaller than the maximum.

---

# 15. Prompt integration

Place retrieved memory in a clearly delimited block.

```text
<retrieved_memory>
The following items are historical project memory. Use only when relevant.
Current repository state and current instructions override stale memory.

[semantic | high confidence]
...
Source: run_123 / src/...

[episodic | successful outcome]
...
Source: run_456
</retrieved_memory>
```

Do not present retrieved memory as system instructions.

Memory is evidence/context, not authority.

---

# 16. Public Python API

Keep the integration surface very small.

```python
from semantic_memory import SemanticMemory

memory = SemanticMemory.from_config("semantic-memory/config/memory.yaml")

context = memory.retrieve(
    text=task,
    project_id="miscellaneous",
    repo_id="agent-monorepo",
    agent_id="planner-agent",
)

prompt_memory = memory.render_context(context)
```

Post-run:

```python
memory.remember(
    project_id="miscellaneous",
    repo_id="agent-monorepo",
    agent_id="planner-agent",
    session_id=session_id,
    task=task,
    final_summary=final_summary,
    outcome="success",
    decisions=decisions,
    resolved_errors=resolved_errors,
    changed_files=changed_files,
    changed_symbols=changed_symbols,
    source_event_id=run_id,
    source_uri=work_log_uri,
    source_commit=git_commit,
)
```

Do not make every agent understand OpenSearch, Bedrock, or embedding details.

---

# 17. Resolver integration

Recommended resolver flow:

```text
user prompt
   |
   v
agent resolver
   |
   +--> resolve agent
   +--> resolve skills
   +--> resolve workflow
   +--> construct memory query
   |
   v
semantic-memory.retrieve()
   |
   v
assemble final agent context
   |
   v
run Codex agent
```

Post-run:

```text
Codex run completes
   |
   v
existing logging/post-completion hook
   |
   +--> save raw run artifacts
   |
   +--> semantic-memory.remember(compact run summary)
   |
   v
finish
```

Memory write failure must not fail the main agent task.

Log it and continue.

---

# 18. Episodic memory in Phase 1

Implement a deliberately lightweight episode record at first.

Store an episode only when the run had meaningful problem-solving value.

Schema content should summarize:

```text
Situation
Intent
Key actions
Outcome
Root cause or important observation
Resolution
Reusable lesson
```

Example:

```text
Situation: Secure Angular route loaded AEM model paths containing duplicate /secure.
Intent: Preserve language prefix while routing secure model requests.
Actions: Inspected Kong rewrite and Angular guard behavior; compared the produced model URL.
Outcome: Success.
Root cause: Both layers inserted /secure.
Resolution: Normalize path and add /secure only when absent.
Reusable lesson: Own a path transformation at one boundary and make rewrites idempotent.
```

Do not store every shell command/tool call in the embedded content.

The raw run log remains available by `source_uri`.

---

# 19. Memory feedback

Retrieval quality improves faster if the system records whether retrieved memory helped.

Phase 1 can capture low-complexity feedback events locally/logging-only:

```json
{
  "query_id": "q_...",
  "memory_id": "mem_...",
  "used": true,
  "helpful": true,
  "reason": "matched root cause"
}
```

Do not mutate memory ranking weights automatically from a handful of feedback events yet.

Use the data for evaluation first.

---

# 20. Security and privacy

## 20.1 Never embed secrets

Before extraction/write, block:

- AWS secret keys;
- bearer tokens;
- session cookies;
- API keys;
- passwords;
- private keys;
- OAuth codes;
- `.env` values recognized as secrets.

If an incident memory needs to mention a credential problem, store the concept:

```text
Deployment failed because the AWS session token had expired.
```

not the token.

## 20.2 OpenSearch security

OpenSearch Serverless requires encryption at rest; security is controlled through encryption, network, and data access policies. Private collections can use VPC endpoints/PrivateLink. [R19][R20]

Production recommendation:

- customer-managed KMS key if organizational policy requires it;
- private network access where practical;
- separate runtime role from infrastructure-admin role;
- runtime role gets read/write only to the required collection/index;
- no wildcard principals;
- no browser/public dashboard dependency for the agent runtime.

## 20.3 Provenance without sensitive metadata

Store identifiers and references needed for debugging, but do not use metadata as a hiding place for sensitive data.

---

# 21. CloudFormation responsibilities

`infra/template.yaml` should create/configure only what semantic memory owns.

Logical resources:

```text
SemanticMemoryCollectionGroup
SemanticMemoryCollection
SemanticMemoryEncryptionPolicy / KMS Key if needed
SemanticMemoryNetworkPolicy
SemanticMemoryDataAccessPolicy
SemanticMemoryRuntimeRole or policy attachment
```

Outputs:

```text
CollectionName
CollectionId
CollectionEndpoint
RuntimeRoleArn
```

The index mapping can be applied by `scripts/bootstrap.py` rather than overcomplicating CloudFormation if the current AWS index resource/API makes iterative schema changes less convenient.

---

# 22. Phase 1 implementation tasks

## Task 1 — Create package skeleton

Create the folder structure from Section 11.

Acceptance:

- importable `semantic_memory` package;
- config loads;
- validation errors are clear.

## Task 2 — AWS infrastructure

Provision dev OpenSearch Serverless NextGen Vector collection.

Acceptance:

- collection active;
- least-privilege runtime identity can connect;
- unauthorized identity cannot read/write;
- encryption/network/data-access policies verified.

## Task 3 — Bedrock embedding client

Implement in `store.py`:

```python
def embed_text(text: str) -> list[float]:
    ...
```

Requirements:

- Titan V2;
- 512 dimensions;
- normalized vectors;
- timeout/retry handling;
- model/version logged;
- no embedding of blank text.

## Task 4 — OpenSearch store

Implement:

```python
create_index_if_missing()
get_memory(memory_id)
find_by_hash(content_hash)
index_memory(record)
update_memory(record)
vector_search(query)
lexical_search(query)
```

Keep functions meaningful; do not break each HTTP call into many one-line helpers.

## Task 5 — Extraction and eligibility

Implement structured candidate extraction and deterministic reject rules.

Test at least:

- useful architecture fact accepted;
- raw log rejected;
- secret rejected;
- duplicate rejected;
- speculative statement rejected;
- trivial status rejected.

## Task 6 — Consolidation

Implement:

```text
ADD / UPDATE / SUPERSEDE / NOOP
```

Acceptance:

- duplicate fact does not create duplicate memory;
- updated architectural truth supersedes old record;
- old record remains queryable historically but is not returned by default.

## Task 7 — Hybrid retrieval

Implement vector + lexical candidate retrieval and application-side RRF.

Acceptance:

- conceptual queries retrieve semantic matches;
- exact symbol/error queries retrieve lexical matches;
- project/repo filters prevent cross-project contamination.

## Task 8 — Context builder

Implement token-budget-aware context formatting.

Acceptance:

- never exceeds configured memory budget;
- zero-result retrieval is valid;
- provenance included compactly;
- duplicate/superseded memories omitted.

## Task 9 — Resolver + post-hook integration

Integrate pre-run retrieval and post-run memory writing.

Acceptance:

- disabling memory returns original workflow behavior;
- memory service failure never blocks the primary agent;
- timing metrics logged.

## Task 10 — Evaluation baseline

Create at least 50–100 project-specific query/memory cases before tuning ranking.

Include:

- exact fact recall;
- semantic paraphrases;
- exact code symbols;
- irrelevant queries where no memory should be injected;
- stale/superseded facts;
- conflicting facts;
- similar facts from different repos;
- failed vs successful episodes.

---

# 23. Phase 1 evaluation

## 23.1 Retrieval metrics

Measure:

```text
Precision@1
Precision@5
Recall@5
MRR
NDCG@K (optional)
```

Precision matters especially because false-positive memory is expensive in an agent prompt.

## 23.2 Memory-system metrics

```text
duplicate memory rate
supersession correctness
stale memory injection rate
cross-project leakage rate
empty-result correctness
average memories injected
tokens injected per task
embedding calls per completed task
write acceptance rate
```

## 23.3 Runtime metrics

```text
p50/p95 embedding latency
p50/p95 OpenSearch retrieval latency
p50/p95 total memory retrieval latency
p50/p95 write-processing latency
```

## 23.4 Downstream A/B evaluation

Run representative agent tasks with:

```text
A: memory disabled
B: semantic memory enabled
```

Compare:

- task success;
- repeated mistakes;
- time/tool calls to solution;
- input tokens;
- incorrect assumptions introduced by memory.

Memory is successful only when it improves the agent, not merely when search metrics look good.

---

# 24. Phase 2 — Advanced memory

Start Phase 2 only after Phase 1 has measured precision and actual agent benefit.

Phase 2 adds richer learning while preserving the same public `SemanticMemory` interface.

---

# 25. Phase 2.1 — Rich episodic memory

Expand episodes to structured records:

```json
{
  "situation": "...",
  "intent": "...",
  "assessment": "...",
  "actions": ["..."],
  "outcome": "success",
  "artifacts": ["..."],
  "failures": ["..."],
  "resolution": "...",
  "lesson": "..."
}
```

The embedded text should still be a compact linearized episode, not raw JSON.

AWS’s current episodic memory guidance similarly recommends retrieving similar episodes/reflections for new tasks and using structured completed episodes rather than storing all raw events as long-term memory. [R7]

## Retrieval rule

Retrieve episodes mainly when the task is problem-solving/troubleshooting/planning.

For straightforward fact queries, prefer semantic facts.

---

# 26. Phase 2.2 — Reflection memory

Run periodic consolidation over episodes.

A reflection is allowed only when it is supported by multiple pieces of evidence.

Initial rule:

```text
minimum supporting episodes: 3
```

A reflection record should contain:

```json
{
  "memory_type": "reflection",
  "content": "...",
  "evidence_memory_ids": ["mem1", "mem2", "mem3"],
  "evidence_count": 3,
  "confidence": 0.91
}
```

Example:

```text
Across multiple secure-routing incidents, duplicated path rewriting was caused by transformations occurring in both gateway and frontend layers. Prefer one owning layer and idempotent normalization.
```

Reflection must never be created from one surprising incident.

---

# 27. Phase 2.3 — Procedural memory promotion

Procedural memory changes agent behavior, so use a stronger promotion gate.

Pipeline:

```text
successful episodes
      |
      v
repeated reflection
      |
      v
candidate procedural improvement
      |
      v
human/code-review or explicit approval
      |
      v
version-controlled skill/runbook update
```

OpenSearch stores:

- skill name;
- summary;
- applicability conditions;
- path to skill file;
- version/commit.

It does **not** become the canonical skill file.

This protects the agent from learning a bad rule from one run.

---

# 28. Phase 2.4 — Temporal and conflict-aware memory

Add explicit validity semantics.

Example chain:

```text
mem_A active 2026-06-01 -> 2026-08-10
mem_B active 2026-08-10 -> now
mem_B.supersedes_id = mem_A
```

Queries normally return only current active memory.

Historical questions can opt into superseded memories.

## Conflict rules

When a new candidate contradicts existing memory:

1. compare evidence source;
2. prefer current repository/config over conversation claim;
3. prefer explicit user/architecture decision over assistant inference;
4. if clearly newer and authoritative, supersede;
5. if ambiguous, preserve both as `needs_review` and inject neither by default.

Never force an LLM to “pick a winner” when the evidence is genuinely ambiguous.

---

# 29. Phase 2.5 — Code-aware invalidation

This is especially valuable for your coding agents.

A technical memory can optionally point to:

```text
source_file
source_symbol
source_commit
source_hash
```

At retrieval time:

```text
if memory references a code symbol
and current source hash != source_hash:
    mark memory as possibly_stale
    do not inject as current fact without revalidation
```

Do not hash entire repositories for every query.

Only validate source-linked memories selected as top candidates.

This keeps memory aligned with code without creating a large code-history subsystem.

---

# 30. Phase 2.6 — Reranking

AWS Bedrock provides reranker models that can reorder retrieved text documents and reduce the amount of less-relevant material passed to the generator. [R21]

Phase 2 retrieval:

```text
vector + lexical retrieval
        |
        v
RRF top 30
        |
        v
Bedrock reranker
        |
        v
policy/staleness/dedup gate
        |
        v
0..8 memories
```

Use reranking only if evaluation proves that it improves precision enough to justify added latency/cost.

Do not call a reranker when the first-stage result set is already tiny and exact.

---

# 31. Phase 2.7 — Query decomposition / agentic retrieval

For complex architecture questions, one query may contain multiple memory needs.

Example:

> “How should the new secure-domain router interact with authentication and AEM model rewriting based on what we already learned?”

Potential subqueries:

```text
authentication gating lessons
secure-domain routing decisions
AEM model rewrite failures
```

AWS Bedrock Knowledge Bases now has agentic retrieval that similarly decomposes complex queries and iterates retrieval, showing the industry direction. [R10]

For this custom memory system, implement only when needed:

```python
subqueries = query_planner.plan(task)
for subquery in subqueries[:3]:
    retrieve(subquery)
merge_and_rerank()
```

Cap subqueries to prevent runaway retrieval cost.

---

# 32. Phase 2.8 — Graph-like relational memory

Do not introduce Neptune in Phase 1.

First add lightweight relations inside OpenSearch:

```json
{
  "entities": ["KongRoute", "AEMModelPath", "SecureHost"],
  "relations": [
    "KongRoute rewrites AEMModelPath",
    "SecureHost uses KongRoute"
  ]
}
```

Only add a graph database if evaluation shows recurring multi-hop failures that vector + lexical + structured metadata cannot solve.

Mem0’s graph-enhanced variant reported an incremental gain over its base memory architecture, which is useful evidence that relations can help, but it does not justify taking on graph infrastructure before a simpler design is measured. [R4]

Possible Phase 2B option if justified:

```text
OpenSearch = semantic/episodic retrieval
Neptune     = canonical entity relations
```

Keep this optional.

---

# 33. Phase 2.9 — Background consolidation

Once write volume grows, move non-critical memory maintenance off the run path.

Possible AWS architecture:

```text
post-completion hook
      |
      v
SQS memory-events
      |
      v
Lambda / container worker
      |
      +--> extract/consolidate
      +--> Bedrock embeddings
      +--> OpenSearch

EventBridge nightly
      |
      +--> reflection generation
      +--> stale memory scan
      +--> duplicate compaction
      +--> metrics report
```

Do not add this until Phase 1 post-run processing is operationally inconvenient.

---

# 34. Memory decay and forgetting

Do not implement a universal “old memory = bad memory” rule.

An architecture decision from nine months ago may still be correct; a deployment status from yesterday may already be obsolete.

Use type-aware policies.

## Semantic facts

- no automatic age-based deletion;
- use validity/supersession/source checks;
- lower ranking if source is known stale.

## Episodes

- older episodes can receive a mild recency penalty;
- successful matching episodes remain retrievable;
- compress very old similar episodes into reflections.

## Reflections

- persist while evidence remains valid;
- supersede when counter-evidence accumulates.

## Short-term events

- retain according to log/audit policy;
- do not automatically promote into long-term memory.

Selective forgetting/conflict resolution should be explicitly evaluated; modern memory benchmarks treat it as a core memory capability. [R5]

---

# 35. Memory importance

Do not ask an LLM for an arbitrary importance number and trust it blindly.

Calculate importance from understandable signals.

Example:

```text
+ confirmed architectural decision
+ explicit user constraint
+ successful root-cause resolution
+ repeated evidence
+ affects multiple components
- temporary status
- single speculative observation
- easy to recover from current repo
```

The model can propose `importance`, but deterministic rules can adjust it.

Possible implementation:

```python
importance = candidate.importance

if candidate.subtype == "architecture_decision":
    importance += 0.10
if candidate.subtype == "resolved_failure":
    importance += 0.05
if candidate.is_transient:
    importance -= 0.30
if candidate.evidence_count >= 3:
    importance += 0.10

importance = max(0.0, min(1.0, importance))
```

Keep the formula small enough to understand.

---

# 36. Multi-agent memory boundaries

A shared vector store does not mean every agent should see every memory.

Recommended levels:

```text
project shared
repo shared
agent private
user-specific (only when actually needed)
```

Examples:

### Shared repo memory

```text
Architecture decisions
API contracts
Known deployment failure patterns
Repository conventions
```

### Agent-specific memory

```text
UI-builder-specific successful design workflow
Planner-agent decomposition lessons
Debugger-agent Selenium diagnostic lessons
```

### Do not duplicate shared memory into each agent namespace

Store once and retrieve using scope filters.

---

# 37. Suggested `service.py` shape

```python
class SemanticMemory:
    """Public facade for writing, retrieving, and rendering agent memory."""

    def __init__(self, config: MemoryConfig, store: MemoryStore, extractor: MemoryExtractor):
        self.config = config
        self.store = store
        self.extractor = extractor

    def remember(self, request: MemoryWriteInput) -> list[MemoryRecord]:
        candidates = self.extractor.extract(request)
        accepted = []

        for candidate in candidates[: self.config.write.max_candidates_per_run]:
            if not self.extractor.is_eligible(candidate):
                continue

            existing = self.store.find_related(candidate, limit=5)
            decision = self.extractor.consolidate(candidate, existing)

            if decision.action == "NOOP":
                continue

            record = self._apply_decision(candidate, decision)
            record.embedding = self.store.embed_text(record.content)
            self.store.save(record)
            accepted.append(record)

        return accepted

    def retrieve(self, query: MemoryQuery) -> MemoryContext:
        vector_results = self.store.vector_search(query)
        lexical_results = self.store.lexical_search(query)
        fused = self._rrf(vector_results, lexical_results)
        selected = self._select_context(query, fused)
        return MemoryContext(memories=selected)

    def render_context(self, context: MemoryContext) -> str:
        ...
```

This is intentionally a small facade. Do not build a framework inside the framework.

---

# 38. Suggested `store.py` AWS implementation shape

Dependencies:

```text
boto3
opensearch-py
requests-aws4auth or AWS SDK-compatible SigV4 signer
pydantic
pyyaml
```

Embedding request:

```python
body = {
    "inputText": text,
    "dimensions": 512,
    "normalize": True,
}

response = bedrock_runtime.invoke_model(
    modelId="amazon.titan-embed-text-v2:0",
    body=json.dumps(body),
)
```

AWS documents this request shape for Titan Text Embeddings V2. [R14]

OpenSearch client should use temporary AWS credentials through the standard AWS credential chain; never place static keys in `memory.yaml`.

---

# 39. Failure handling

Memory is an enhancement, not a single point of failure.

## Retrieval failure

```text
log warning
return empty MemoryContext
continue agent run
```

## Embedding failure on write

```text
log failed memory event
keep raw run log as evidence
continue
```

## OpenSearch write failure

Phase 1:

```text
log locally/existing agent logging system
continue
```

Phase 2:

```text
send to retry/dead-letter queue
```

## Extraction model returns invalid output

```text
validate
reject invalid candidates
never write partially parsed memory
```

---

# 40. Observability

Every memory retrieval should log a compact trace:

```json
{
  "query_id": "mq_...",
  "agent_id": "planner-agent",
  "project_id": "miscellaneous",
  "vector_candidates": 20,
  "lexical_candidates": 20,
  "selected": 4,
  "selected_ids": ["mem1", "mem2", "mem3", "mem4"],
  "memory_tokens": 930,
  "latency_ms": 143
}
```

Every memory write:

```json
{
  "source_event_id": "run_...",
  "candidates": 5,
  "accepted": 2,
  "noop": 2,
  "rejected": 1,
  "actions": ["ADD", "SUPERSEDE"]
}
```

Do not log the embedding vectors.

---

# 41. Cost-efficiency rules

1. **Do not embed raw logs.**
2. **Embed only accepted candidates.**
3. Start with **512 dimensions** and benchmark 1024 only if needed.
4. Use exact `content_hash` before semantic duplicate search.
5. Batch backfills rather than invoking one request per old log when possible.
6. Cap candidates per completed run.
7. Cap retrieval candidates.
8. Cap injected memory tokens.
9. Rerank only when first-stage candidate volume justifies it.
10. Use NextGen scale-to-zero for non-continuous/dev workloads where cold-start latency is acceptable. AWS documents a cold wake-up period for scale-to-zero, so production interactive workloads may choose a non-zero minimum capacity. [R12]

AWS notes that Bedrock embedding quotas are request-based, so capacity planning should consider request rate as well as total text volume. [R13]

---

# 42. Memory quality rules — the “anti-noise contract”

A memory may be injected only when all are true:

```text
1. Correct scope
2. Active/current status
3. Relevant to current task
4. Not superseded
5. Not a near-duplicate of a stronger memory
6. Sufficient confidence
7. Source/provenance available
8. Fits context budget
9. Not contradicted by current live source
```

A memory may be written only when all are true:

```text
1. Future usefulness
2. Evidence-backed
3. Self-contained
4. Not secret/sensitive
5. Not trivial/transient
6. Not duplicate
7. Correct scope/type
8. Clear provenance
```

These two contracts should be kept near the code and in tests.

---

# 43. Example end-to-end flow

User asks:

```text
Update the Kong model path rewrite so /secure is inserted after language, but don't duplicate it if already present.
```

Resolver builds query:

```text
Kong AEM model rewrite language en/fr secure path avoid duplicate /secure
```

OpenSearch retrieval returns:

```text
1. Previous failure: duplicate /secure occurred when both gateway and frontend added it.
2. Current architecture fact: secure model route is /content/.../(en|fr)/secure/...model.json.
3. Episode: prior successful idempotent normalization approach.
```

Agent receives only these compact memories plus live code.

After successful work, post-hook extracts:

```text
Candidate: Kong path transformation is idempotent: detect /secure after language before inserting it.
```

Consolidation sees an existing equivalent memory and chooses `UPDATE` evidence rather than ADD.

The index remains compact.

---

# 44. What not to build

Avoid these early mistakes:

## “Embed every conversation chunk”

This is conversation search, not high-quality agent memory.

## “Store all source code in memory”

Use repository search/code indexing for source code. Semantic memory should capture lessons, decisions, and stable relationships.

## “Always retrieve top 10”

This guarantees prompt pollution.

## “One memory namespace for all projects”

This creates cross-project contamination.

## “Automatically rewrite skills from episodes”

This makes behavior drift difficult to audit.

## “Delete contradicted facts”

Supersede instead when history has value.

## “Add a graph database immediately”

Measure whether multi-hop relational failures actually justify it.

## “Use vector similarity as the only relevance signal”

Technical work benefits from exact keyword/symbol matching and metadata filters.

---

# 45. Rollout plan

## Milestone 0 — Evaluation set first

Before production retrieval, curate initial memory/eval examples from recent agent work.

Deliverable:

```text
tests/fixtures/memory_eval.jsonl
```

## Milestone 1 — Storage + embedding

Deliver:

- dev OpenSearch collection;
- Titan embedding client;
- index mapping;
- smoke test.

## Milestone 2 — Controlled writes

Deliver:

- extraction;
- eligibility;
- dedupe;
- ADD/UPDATE/SUPERSEDE/NOOP.

Run on historical logs in dry-run mode first; inspect proposed memories before indexing.

## Milestone 3 — Retrieval

Deliver:

- metadata-filtered vector search;
- lexical search;
- RRF;
- token budget.

## Milestone 4 — Agent integration

Enable memory for one agent first, preferably a technically focused agent with repeated workflows.

Feature flag:

```text
SEMANTIC_MEMORY_ENABLED=true|false
```

## Milestone 5 — Measure

Run A/B tasks and inspect:

- false positives;
- stale memories;
- repeated mistakes prevented;
- context-token cost.

## Milestone 6 — Expand

Enable repo/project-shared memory for additional agents.

## Milestone 7 — Phase 2

Only after Phase 1 is demonstrably helpful, add:

- rich episodic records;
- reflections;
- reranking;
- code-aware invalidation;
- procedural promotion;
- optional async maintenance.

---

# 46. Initial success criteria

Treat these as engineering targets to tune, not industry guarantees.

Phase 1 should aim for:

```text
Precision@5                  >= 0.85 on project eval set
Cross-project leakage       = 0
Superseded-memory injection < 1%
Secret write incidents      = 0
Average injected memories   <= 5
Average memory tokens       <= 1,500 for normal tasks
Memory failure blocks task  = never
```

More important than any single metric:

> On representative repeated engineering tasks, the memory-enabled agent should solve problems with fewer repeated mistakes without introducing stale assumptions.

---

# 47. Phase 2 success criteria

Add:

```text
reflection precision
correct conflict resolution
episode reuse success rate
procedural-promotion acceptance rate
stale-code-memory detection rate
reranker lift over Phase 1
memory-token reduction at equal/better task success
```

MemoryAgentBench’s emphasis on accurate retrieval, learning/adaptation, long-range understanding, and forgetting/conflict handling is a good conceptual checklist for the broader evaluation suite. [R5]

---

# 48. Recommended final architecture

```text
                          ┌─────────────────────────┐
                          │ User / agent task       │
                          └────────────┬────────────┘
                                       │
                                       v
                          ┌─────────────────────────┐
                          │ Agent Resolver          │
                          │ agent + skills + flow   │
                          └────────────┬────────────┘
                                       │
                        memory query   │
                                       v
                    ┌──────────────────────────────┐
                    │ semantic-memory/service.py   │
                    └──────────┬───────────┬───────┘
                               │           │
                    embed/query│           │vector + lexical
                               v           v
                    ┌──────────────┐  ┌───────────────────────┐
                    │ Bedrock      │  │ OpenSearch Serverless │
                    │ Titan V2     │  │ agent-memory-v1       │
                    └──────────────┘  └───────────────────────┘
                                             │
                                             v
                                   filtered compact memories
                                             │
                                             v
                                   ┌────────────────────┐
                                   │ Codex agent prompt │
                                   └─────────┬──────────┘
                                             │
                                             v
                                   completed agent run
                                             │
                                             v
                                   ┌────────────────────┐
                                   │ existing run logs  │
                                   │ / S3 evidence      │
                                   └─────────┬──────────┘
                                             │
                                             v
                             extraction -> consolidation
                                             │
                                             v
                                      OpenSearch write
```

Phase 2 adds reflection/reranking/invalidation around this architecture without replacing it.

---

# 49. Key design decisions

| Decision | Recommendation | Reason |
|---|---|---|
| Vector store | OpenSearch Serverless NextGen | AWS-native vector search, filters, hybrid capability, managed capacity |
| Embeddings | Titan Text Embeddings V2 | AWS-native, retrieval-focused, selectable dimensions |
| Initial dimensions | 512 | lower footprint; benchmark before increasing |
| Number of indexes | one long-term memory index initially | simplest filtering and operations |
| Raw logs | keep outside memory index | evidence/archive, not prompt memory |
| Write behavior | selective extraction + consolidation | prevents noise/duplicates |
| Conflict behavior | supersede, do not normally delete | preserves history |
| Retrieval | vector + BM25 + RRF | semantic + exact technical terms |
| Prompt policy | small bounded memory block | avoids context pollution |
| Episodic memory | lightweight Phase 1, richer Phase 2 | value without early complexity |
| Procedural memory | Git files are authoritative | auditable behavior changes |
| Graph memory | optional later | complexity must be justified by eval |
| Reranker | Phase 2, evidence-driven | added cost/latency |
| Agent integration | one Python facade | agents do not know storage details |

---

# 50. Research references

Accessed September 2026 unless publication date is shown.

**[R1] Cognitive Architectures for Language Agents (CoALA).** Sumers et al., 2023.  
https://arxiv.org/abs/2309.02427

**[R2] MemGPT: Towards LLMs as Operating Systems.** Packer et al., 2023.  
https://arxiv.org/abs/2310.08560

**[R3] Generative Agents: Interactive Simulacra of Human Behavior.** Park et al., 2023.  
https://arxiv.org/abs/2304.03442

**[R4] Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory.** Chhikara et al., 2025; publication page updated 2026.  
https://arxiv.org/abs/2504.19413

**[R5] Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions / MemoryAgentBench.** Hu et al., ICLR 2026.  
https://arxiv.org/abs/2507.05257  
https://github.com/HUST-AI-HYZ/MemoryAgentBench

**[R6] Amazon Bedrock AgentCore — Semantic memory strategy.**  
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/semantic-memory-strategy.html

**[R7] Amazon Bedrock AgentCore — Episodic memory strategy.**  
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html

**[R8] Amazon Bedrock AgentCore — Memory strategies / memory types.**  
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html  
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html

**[R9] Amazon Bedrock Knowledge Bases — How knowledge bases work.**  
https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-it-works.html

**[R10] Amazon Bedrock Knowledge Bases — Agentic retrieval.**  
https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html

**[R11] Amazon OpenSearch Serverless — Creating NextGen collections / Vector Search.**  
https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-create.html

**[R12] Amazon OpenSearch Serverless — Scale to zero.**  
https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scale-to-zero.html

**[R13] Amazon Bedrock — Titan Text Embeddings models.**  
https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html

**[R14] Amazon Bedrock — Titan Text Embeddings V2 request/model documentation.**  
https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html

**[R15] Amazon OpenSearch — k-NN search and `knn_vector`.**  
https://docs.aws.amazon.com/opensearch-service/latest/developerguide/knn.html

**[R16] OpenSearch — Efficient k-NN filtering / filtered vector search.**  
https://docs.opensearch.org/latest/vector-search/filter-search-knn/efficient-knn-filtering/  
https://docs.opensearch.org/latest/vector-search/filter-search-knn/

**[R17] OpenSearch — Hybrid search.**  
https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/

**[R18] OpenSearch — Reciprocal rank fusion.**  
https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/

**[R19] Amazon OpenSearch Serverless — Security overview.**  
https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-security.html

**[R20] Amazon OpenSearch Serverless — Data access control.**  
https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html

**[R21] Amazon Bedrock — Reranker models.**  
https://docs.aws.amazon.com/bedrock/latest/userguide/rerank.html

---

# 51. Final recommendation

Build Phase 1 as a **small, strict memory layer** rather than a general knowledge platform:

```text
OpenSearch + Titan embeddings
        +
selective post-run extraction
        +
consolidation/supersession
        +
metadata-filtered hybrid retrieval
        +
small prompt budget
        +
provenance and evaluation
```

The most important implementation rule is:

> **Store less, but store better. Retrieve broadly, but inject narrowly.**

Once this baseline proves measurable value, Phase 2 can safely add episodic reflection, code-aware staleness checks, reranking, procedural promotion, and optional relational memory without turning the memory subsystem into an opaque or noisy dependency.
