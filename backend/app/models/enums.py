from enum import StrEnum


class CaptureMode(StrEnum):
    OFF = "off"
    CAPTURE = "capture"
    ANALYZE = "analyze"


class SubmissionSource(StrEnum):
    EXTENSION = "extension"
    PASTE = "paste"
    IMPORT = "import"


class SubmissionStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    REVIEWED = "reviewed"
    FAILED = "failed"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageStatus(StrEnum):
    STREAMING = "streaming"
    DONE = "done"
    FAILED = "failed"


class ImportAnalysisMode(StrEnum):
    FULL = "full"
    TAGS_ONLY = "tags_only"
    NONE = "none"


class ImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
