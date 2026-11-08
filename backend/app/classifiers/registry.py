"""Choose the model backend from CLASSIFIER_BACKEND (brief)."""

from app.classifiers.base import EnquiryClassifier
from app.classifiers.keyword import KeywordClassifier
from app.classifiers.stub import StubLLMClassifier
from app.core.config import Settings


def get_model_backend(settings: Settings) -> EnquiryClassifier:
    """The backend asked for a proposal in pipeline step 3. With "keyword" the keyword
    result is used directly and no model is called."""
    if settings.classifier_backend == "stub":
        return StubLLMClassifier()
    return KeywordClassifier()
