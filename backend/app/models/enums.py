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
    IMPORTED = "imported"  # imported from GitHub, not analysed yet


class ReviewKind(StrEnum):
    FULL = "full"  # verdict + four tiers
    TAGS = "tags"  # technique and complexity only (the cheap import pass)


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
    CANCELLED = "cancelled"
