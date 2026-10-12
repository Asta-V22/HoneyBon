"""Read past solutions from a public GitHub repository in the LeetHub layout.

The whole repository is downloaded as one tarball from codeload.github.com, which (unlike the
REST API) has no 60-requests-an-hour limit for anonymous callers. Nothing is extracted to disk:
members are read in memory, and only small code files and the first bytes of each README are
looked at. READMEs hold LeetCode's problem statement, so only the title and difficulty are taken
from them; the statement itself is never stored.
"""

import gzip
import html
import io
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import httpx

ARCHIVE_URL = "https://codeload.github.com/{repo}/tar.gz/HEAD"
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_CODE_BYTES = 100_000
MAX_MEMBERS = 50_000
MAX_UNMATCHED = 200

# File extension -> the language names the rest of the app uses.
LANGUAGES = {
    ".py": "python",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cs": "csharp",
    ".rb": "ruby",
    ".scala": "scala",
    ".php": "php",
    ".dart": "dart",
    ".sql": "sql",
}

_REPO = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})"
    r"(?:\.git)?/?(?:[?#].*)?$|^([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})$"
)
# LeetHub folders: "<LeetCode internal question ID>-<slug>", sometimes zero-padded ("0001-two-sum").
_FOLDER = re.compile(r"^(\d{1,5})-([a-z0-9]+(?:-[a-z0-9]+)*)$")
_README_TITLE = re.compile(
    r'<h2>\s*<a href="https://leetcode\.com/problems/([a-z0-9-]+)/?"\s*>\s*(?:\d+\.\s*)?([^<]{1,300})</a>'
)
_README_DIFFICULTY = re.compile(r"Difficulty-(Easy|Medium|Hard)|<h3>\s*(Easy|Medium|Hard)\s*</h3>")


class RepoUnavailable(Exception):
    """The repository could not be read; the message is shown to the user."""


def parse_repo(text: str) -> str:
    """'https://github.com/owner/name' or 'owner/name' -> 'owner/name'."""
    m = _REPO.match(text.strip())
    if not m:
        raise ValueError("Enter a GitHub repository like https://github.com/you/leetcode.")
    owner, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    name = name.removesuffix(".git")
    if name in (".", ".."):
        raise ValueError("Enter a GitHub repository like https://github.com/you/leetcode.")
    return f"{owner}/{name}"


@dataclass(frozen=True)
class SolutionFile:
    path: str  # inside the repository
    language: str
    code: str


@dataclass
class ProblemFolder:
    folder: str
    slug: str
    question_id: str  # LeetCode's internal ID (not the visible number)
    title: str | None = None
    difficulty: str | None = None
    files: list[SolutionFile] = field(default_factory=list)


@dataclass
class RepoContents:
    problems: list[ProblemFolder]
    # Folders with code that do not follow the "<id>-<slug>" layout, for manual mapping.
    unmatched: list[dict]


async def download_archive(repo: str, transport: httpx.AsyncBaseTransport | None = None) -> bytes:
    url = ARCHIVE_URL.format(repo=repo)
    try:
        async with httpx.AsyncClient(
            timeout=60, transport=transport, follow_redirects=True
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code == 404:
                    raise RepoUnavailable(
                        f"GitHub has no public repository {repo}. Check the name, or make the "
                        "repository public."
                    )
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise RepoUnavailable("The repository is too large to import (over 30 MB).")
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise RepoUnavailable(f"Couldn't download the repository from GitHub: {exc}") from exc
    return b"".join(chunks)


def _decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def parse_archive(data: bytes) -> RepoContents:
    try:
        # Decompress with a cap so a hostile archive can't exhaust memory.
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            raw = gz.read(MAX_UNPACKED_BYTES + 1)
        if len(raw) > MAX_UNPACKED_BYTES:
            raise RepoUnavailable("The repository is too large to import.")
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise RepoUnavailable("GitHub sent something that isn't a repository archive.") from exc

    problems: dict[str, ProblemFolder] = {}
    unmatched: dict[str, list[SolutionFile]] = {}
    readmes: dict[str, str] = {}
    with archive:
        for count, member in enumerate(archive):
            if count >= MAX_MEMBERS:
                break
            if not member.isfile():  # skips links, devices and directories
                continue
            parts = PurePosixPath(member.name).parts[1:]  # drop the "<repo>-<sha>/" prefix
            if len(parts) < 2 or any(p in ("..", "") or p.startswith(".") for p in parts):
                continue  # root files, hidden folders (.github), odd paths
            path = "/".join(parts)
            folder, filename = parts[-2], parts[-1]
            suffix = PurePosixPath(filename).suffix.lower()
            is_readme = filename.lower() == "readme.md"
            language = LANGUAGES.get(suffix)
            if not is_readme and (language is None or member.size > MAX_CODE_BYTES):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            text = _decode(handle.read(4096 if is_readme else MAX_CODE_BYTES))
            if text is None:
                continue
            m = _FOLDER.match(folder)
            if is_readme:
                if m:
                    readmes[path.rsplit("/", 1)[0]] = text
                continue
            if not text.strip():
                continue
            solution = SolutionFile(path=path, language=language, code=text)
            parent = path.rsplit("/", 1)[0]
            if m:
                problem = problems.get(parent)
                if problem is None:
                    problem = problems[parent] = ProblemFolder(
                        folder=folder, slug=m.group(2), question_id=str(int(m.group(1)))
                    )
                problem.files.append(solution)
            else:
                unmatched.setdefault(parent, []).append(solution)

    for parent, problem in problems.items():
        if readme := readmes.get(parent):
            _apply_readme(problem, readme)
    return RepoContents(
        problems=sorted(problems.values(), key=lambda p: (int(p.question_id), p.folder)),
        unmatched=[
            {
                "folder": parent,
                "files": [{"path": f.path, "language": f.language, "code": f.code} for f in files],
            }
            for parent, files in sorted(unmatched.items())[:MAX_UNMATCHED]
        ],
    )


def _apply_readme(problem: ProblemFolder, readme: str) -> None:
    """Title and difficulty from LeetHub's README header; the statement below it is ignored."""
    if m := _README_TITLE.search(readme):
        problem.slug = m.group(1)
        problem.title = html.unescape(m.group(2)).strip()
    if m := _README_DIFFICULTY.search(readme):
        problem.difficulty = m.group(1) or m.group(2)
