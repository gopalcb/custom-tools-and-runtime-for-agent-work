# Embeddings

Semantic retrieval is deferred until memory volume shows that lexical matching
is insufficient. A future adapter should satisfy this contract:

```python
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Local, Bedrock, or OpenAI implementations may sit behind that protocol. There
are intentionally no provider classes or runtime dependencies at this stage.
