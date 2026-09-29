"""Test doubles shared by several test files. Plain classes, not fixtures."""

from types import SimpleNamespace
from typing import Any


class FakeClient:
    """Stands in for anthropic.Anthropic. No network: it returns the answers it was given,
    in order, and records every request so tests can inspect what would have been sent."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.messages = self  # so that client.messages.create(...) lands on create below

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.answers.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=300),
            stop_reason="end_turn",
        )
