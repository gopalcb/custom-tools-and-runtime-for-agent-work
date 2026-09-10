# Stores

The initial runtime reads repository files and uses append-only run state. A
future store adapter should provide a narrow record contract such as:

```python
class MemoryStore(Protocol):
    async def put(self, records: list[dict[str, object]]) -> None: ...
    async def query(self, filters: dict[str, object]) -> list[dict[str, object]]: ...
```

Filesystem, database, or hosted adapters can be added after a measured need.
There are intentionally no empty store classes or separate memory SDK now.
