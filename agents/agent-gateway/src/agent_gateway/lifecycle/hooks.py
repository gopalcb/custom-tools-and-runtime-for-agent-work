from __future__ import annotations


class AgentLifecycleHooks:
    """Extension point for observer/logging hooks added after V1."""

    def before_run(self, context: dict) -> None:
        pass

    def after_run(self, context: dict, result: object) -> None:
        pass

    def on_failure(self, context: dict, error: Exception) -> None:
        pass
