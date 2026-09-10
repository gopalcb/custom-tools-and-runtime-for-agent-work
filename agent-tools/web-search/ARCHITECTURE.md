# Web Search Architecture

This tool is a small Codex SDK adapter. It sends a bounded research prompt and
developer instruction to the shared `CodexSDKClient`, which is the only layer
that owns Codex protocol details. It returns a JSON-compatible object with a
query, answer, and source list, then can render that object to Markdown. It
does not launch Selenium, reuse browser profiles, scrape web pages, or maintain
a second provider implementation.

`cli.py` builds a `SearchRequest`, calls `service.search`, saves the rendered
Markdown under `output/`, and prints the JSON response plus output path.
`model.py` owns request/response data structures, `validation.py` validates the
service boundary, and `service.py` owns the Codex call and Markdown conversion.
The runtime uses the same Codex-backed research behavior through its
`web_search` workflow tool.
