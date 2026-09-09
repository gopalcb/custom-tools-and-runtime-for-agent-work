from __future__ import annotations


def assemble_context(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
