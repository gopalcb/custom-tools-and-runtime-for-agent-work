monorepo/
│
├── agents/
│   ├── agent-builder/
│   ├── agent-ui-builder/
│   ├── planner-agent/
│   └── ...

└── .agent-state/
│   ├── cache/
│   ├── logs/
│   ├── sessions/

├── agent-gateway/
│       ├── gateway.py
│       ├── models.py
│       ├── registry.py
│       ├── loader.py
│       ├── runtime.py
│       ├── lifecycle.py
│       ├── memory.py
│       ├── skills.py
│       ├── context.py
│       ├── providers.py
│
├── agent-runtime/
│   └── agent-monorepo/
│       ├── bootstrap.py
│       ├── resolver.py
|       │
        ├── logging/
        │   ├── event_logger.py
        │   ├── event_store.py
        │   └── event_types.py
        │
        ├── hooks/
        │   └── post_completion.py
|       |
│       │
│       └── memory/
│           ├── memory_service.py
│           ├── memory_types.py
│           ├── memory_policy.py
            ├── memory_extractor.py
│           │
│           ├── ingestion/ -- keep it blank for now
│           │
│           ├── retrieval/
│           │   ├── retriever.py
│           │   ├── hybrid_search.py
│           │   └── reranker.py
│           │
│           ├── embeddings/ -- keep the structure but don't implement anything for now
│           │   ├── embedding_provider.py
│           │   ├── local_provider.py
│           │   ├── bedrock_provider.py
│           │   └── openai_provider.py
│           │
│           └── stores/ -- keep the structure but don't implement anything for now
│               ├── memory_store.py
│               ├── pgvector_store.py
│               ├── agentcore_store.py
│               └── s3_vector_store.py
│
└── packages/
    └── agent-memory-sdk/



# Logging architecture

Agent
 │
 ▼
Agent Runtime
 │
 ├── EventLogger
 │       └── events.jsonl
 │
 ├── Agent execution
 │
 └── PostCompletionHook
          │
          ├── run.json
          ├── summary.md
          ├── metrics
          └── memory extraction
                    │
                    ▼
              Memory Store

Use a Python/runtime logging layer, not another AI agent, for generating the raw interaction event log.

The cleanest design is:

Agent runtime
   │
   ├─ before prompt/model call ──► log event
   ├─ after model response ──────► log event
   ├─ before tool call ──────────► log event
   ├─ after tool result ─────────► log event
   ├─ on error ─────────────────► log event
   │
   └─ post-completion hook
           │
           ├─ finalize run
           ├─ calculate metrics
           ├─ generate run summary
           └─ trigger memory extraction

The important distinction is:

Python/runtime instrumentation = authoritative event logging
Post-hook = run finalization and higher-level processing

Best split

Use your Python runtime to write events immediately as they happen:

logger.emit(
    event_type="model_request",
    run_id=run_id,
    agent_id=agent_id,
    payload={
        "prompt": prompt,
        "context_refs": context_refs
    }
)

Then:
logger.emit(
    event_type="model_response",
    run_id=run_id,
    agent_id=agent_id,
    payload={
        "response": response,
        "tokens": token_usage
    }
)

Tool calls similarly:
logger.emit(
    event_type="tool_call",
    payload={
        "tool": "shell",
        "args": command
    }
)

logger.emit(
    event_type="tool_result",
    payload={
        "tool": "shell",
        "exit_code": 0,
        "output": result
    }
)
And errors:
logger.emit(
    event_type="error",
    payload={
        "type": type(exc).__name__,
        "message": str(exc)
    }
)
Write these incrementally to:
events.jsonl
For example:
{"seq":1,"type":"run_started","ts":"..."}
{"seq":2,"type":"model_request","ts":"..."}
{"seq":3,"type":"model_response","ts":"..."}
{"seq":4,"type":"tool_call","ts":"..."}
{"seq":5,"type":"tool_result","ts":"..."}
{"seq":6,"type":"run_completed","ts":"..."}

JSONL is ideal here because you can append safely without rewriting the whole file.

Then use the post-completion hook

Your post-hook should do things that require the full run to be finished.

For your existing architecture, I'd have:

post_completion.py

do this:

def post_completion(run_id: str):
    events = event_store.load_run(run_id)

    finalize_run_metadata(events)

    calculate_metrics(events)

    write_summary(events)

    extract_memory_candidates(events)

    upload_logs_if_configured(events)

The post-hook can generate:

run.json
events.jsonl
summary.md
artifacts.json
memory_candidates.json

So:

run-123/
├── run.json
├── events.jsonl
├── summary.md
├── artifacts.json
└── memory_candidates.json -- keep it but don't implement for now

One particularly important implementation detail: do not rely only on the post-hook for event collection. If the agent crashes halfway through, you lose the most interesting debugging information.

Emit events continuously during execution, then let the post-hook finalize whatever exists.

So the rule I'd use is:

Runtime records facts. Post-hook organizes them. AI learns from them.