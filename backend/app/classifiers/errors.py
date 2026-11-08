"""Ways a model backend can fail. The pipeline turns each into a fallback, never a lost
enquiry (brief: failure handling)."""


class ClassifierError(Exception):
    code = "classifier_error"


class ClassifierTimeout(ClassifierError):
    """The provider did not answer within the timeout."""

    code = "timeout"


class ClassifierUnavailable(ClassifierError):
    """The provider returned an error (down, rate limited, key rejected)."""

    code = "provider_error"


class InvalidModelOutput(ClassifierError):
    """The output was still not valid JSON for the schema after one retry."""

    code = "invalid_output"
