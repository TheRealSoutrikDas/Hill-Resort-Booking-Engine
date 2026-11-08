"""Choose the model backend from CLASSIFIER_BACKEND (brief: one adapter)."""

from app.classifiers.base import EnquiryClassifier
from app.classifiers.gemini import GeminiClassifier
from app.classifiers.keyword import KeywordClassifier
from app.core.config import Settings


def get_model_backend(settings: Settings) -> EnquiryClassifier:
    """The backend asked for a proposal in pipeline step 3. With "keyword" the keyword
    result is used directly and no model is called."""
    if settings.classifier_backend == "gemini":
        # Settings already refused to start without a key (A-130).
        return GeminiClassifier(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_seconds,
        )
    return KeywordClassifier()
