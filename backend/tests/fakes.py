"""Test double for a model backend (moved out of the app in step 22, D-45).

`StubLLMClassifier` returns the keyword result relabelled "stub", or simulates a
failure, so every pipeline path can be tested without a provider. The real backend
(`app.classifiers.gemini`) is tested separately against a fake HTTP transport.
"""

from dataclasses import replace
from datetime import date
from typing import Literal

from app.classifiers.base import OWNER_FOR, ClassificationResult
from app.classifiers.errors import ClassifierTimeout, ClassifierUnavailable, InvalidModelOutput
from app.classifiers.keyword import KeywordClassifier
from app.classifiers.templates import DRAFTS

StubMode = Literal["echo", "timeout", "provider_error", "invalid_output"]


class StubLLMClassifier:
    name = "stub"

    def __init__(
        self,
        mode: StubMode = "echo",
        category: str | None = None,
        confidence: float | None = None,
    ) -> None:
        self.mode = mode
        self.category = category
        self.confidence = confidence
        self.received: list[tuple[str, date]] = []  # exactly what a provider would be sent

    def classify(self, message: str, received_on: date) -> ClassificationResult:
        self.received.append((message, received_on))
        if self.mode == "timeout":
            raise ClassifierTimeout("stub: simulated timeout")
        if self.mode == "provider_error":
            raise ClassifierUnavailable("stub: simulated provider error")
        if self.mode == "invalid_output":
            raise InvalidModelOutput("stub: simulated invalid output after one retry")
        base = KeywordClassifier().classify(message, received_on)
        category = self.category or base.category
        result = replace(
            base,
            category=category,
            owner=OWNER_FOR[category],
            confidence=self.confidence if self.confidence is not None else base.confidence,
            draft_template=DRAFTS[category],
            backend=self.name,
            complaint_signal=False,  # only the keyword backend reports this signal
        )
        return replace(
            result, raw_output={"stub": True, "category": category, "confidence": result.confidence}
        )
