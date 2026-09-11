# Architecture

## Purpose

`agent-logs-analyzer` watches `.agent-state/logs/system/**/*.log` for fresh
`ERROR` lines, emits durable RuntimeEvent records, and passes exact log error
objects to the shared internal messaging bus for active tracking and
escalation.

## Project Structure

`agent.yaml`
Declarative runtime definition for the analyzer agent.

`instructions.md`
Behavioral instructions for analyzing log errors and documenting findings.

`log_analyzer.py`
Python background tailer started from shared runtime bootstrap.

## Main Execution Flow

`agent-runtime/agent-monorepo/bootstrap.py` loads `log_analyzer.py` by file path
on every custom Codex startup. The analyzer checks whether a thread is already
alive for the project root. If it is running, startup continues without doing
anything. If not, the analyzer starts a daemon thread.

On thread startup, existing log files are positioned at end-of-file so only new
lines are processed. Newly created log files are read from the beginning. Each
fresh line containing `ERROR` is converted into a bounded error object with the
raw line, source log path, line number, and nearby context. The object is sent
unchanged as an `error.detected` message, updates
`.agent-state/agents-messaging/current-error.json`, and is reported through the
shared RuntimeEvent contract.

## Module Responsibilities

`log_analyzer.py`
Owns thread lifecycle, system log polling, exact error-object construction,
message-bus handoff, and RuntimeEvent emission for the background analyzer run.

## Configuration

The analyzer uses repository-relative defaults:

- Logs: `.agent-state/logs/system/`
- Active error: `.agent-state/agents-messaging/current-error.json`
- Error archive: `.agent-state/agents-messaging/errors/`
- Runtime events: configured project `.agent-state`

No external watcher dependency is required.

## Data Flow

System log line -> exact error object -> MessageBus `error.detected` message
and current-error record -> RuntimeEvent records under
`.agent-state/logs/system-log-analyzer/log-analyzer-yyyy-mm-dd/`.

## Extension Points

Add consumers to the shared messaging bus when a new escalation target is
needed. Keep this analyzer focused on detecting fresh log errors and handing off
the exact error object.
