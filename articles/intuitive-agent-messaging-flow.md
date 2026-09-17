# Agent Messaging as the System's Nervous System

Agent messaging is easiest to understand if you stop thinking of it as chat.

In this system, a message is a small work envelope. It says who sent it, what
topic it belongs to, what payload it carries, and where the result should be
recorded. The message queue does not need to know everything about every tool.
It only needs to accept the envelope, persist its state, and hand it to the
right deterministic handler.

That is the important idea: tools are called by routing messages.

Generated diagrams for this article:

- [intuitive-agent-messaging-flow-diagrams.html](intuitive-agent-messaging-flow-diagrams.html)
- [intuitive-agent-messaging-flow-diagrams.yaml](intuitive-agent-messaging-flow-diagrams.yaml)

## A Message Is a Work Envelope

The compact MQ server accepts a request with four simple parts:

- `topic`: the route, such as `read-file`, `run-workflow`, or `memory-store`.
- `sender`: the agent, workflow, or caller that produced the request.
- `payload`: the arguments for the route.
- `event_id`: an optional stable id; if it is missing, the server creates one.

The server turns that request into an event. The event gets a status, a
timestamp, and a result slot. Then it is saved before anything risky happens.

That first save matters. Even if processing fails later, the system still has a
record that someone asked for work.

## The Flow Is Small on Purpose

The lifecycle is:

1. A caller posts a message.
2. The server builds an event.
3. The event is stored as `pending`.
4. The event enters the queue.
5. A worker marks it `processing`.
6. The handler reads the topic.
7. The matching tool function runs.
8. The result is attached.
9. The event is stored as `processed`.

Nothing magical is hiding in the middle. The handler is a topic switchboard.
`read-file` reads a safe project file. `write-file` writes one. `run-workflow`
resolves workflow YAML. `memory-store` records memory. `invoke-function` calls a
small allow-listed helper such as `health` or `web-search`.

## How Tool Calls Ride on Messaging

A tool call is just a message whose topic points at a tool-shaped handler.

For example, a workflow can contain:

```yaml
uses: message
topic: invoke-function
payload:
  name: web-search
```

The workflow runner does not need a special web-search branch. It can treat the
step as a message step. The MQ handler receives `topic: invoke-function`, reads
`payload.name`, and dispatches the allowed helper.

The same shape works for memory, workflow resolution, file operations, and
task creation. The system gets one common path for tool-like work:

```text
agent or workflow -> message envelope -> topic handler -> tool result -> durable event
```

## Why This Feels Different From Direct Calls

A direct function call disappears when the process exits unless someone records
it. A message creates evidence as part of the call.

That gives the system a useful timeline:

- who asked for the work;
- which route handled it;
- what arguments were provided;
- whether it was pending, processing, or processed;
- what result came back.

This is why messaging is a good fit for local agent systems. Agents can stay
creative and high-level, while tools stay bounded and inspectable.

## Two Kinds of Messaging

There are two related messaging shapes in `my-system-libs`.

The compact MQ server is for topic-dispatched runtime work. It stores event
snapshots under `.agent-state/messages/` and is best for deterministic actions:
files, memory, workflow resolution, health checks, tasks, and small helper
functions.

The file-backed agent message bus under `agent-custom-tools/event-messaging/`
is for agent-to-agent inbox behavior. It has inbox, processed, failed, record,
thread, task, and error state. It is useful when one named agent needs another
named agent or tool-like worker to respond later.

They share the same philosophy: the important movement should be visible on
disk.

## The Handler Is the Boundary

The handler is where freedom becomes discipline.

An agent can ask for work in natural language before it reaches this layer, but
the handler only accepts known topics. Unknown topics fail. File paths are kept
inside the project root. Memory actions are reduced to store, search, and
health. Helper functions are allow-listed.

That boundary is what makes messaging practical. The agent can decide what it
wants. The system decides what is allowed.

## The Mental Model

Think of the message queue as a small desk in the middle of the runtime.

Agents, workflows, and operator surfaces put labeled envelopes on the desk. The
worker opens one envelope at a time. The topic tells it which tool shelf to use.
The payload gives the arguments. The result goes back into the envelope. The
envelope is filed where the operator and future tools can inspect it.

That is agent messaging in this system. It is not a second brain. It is the
visible movement of work.
