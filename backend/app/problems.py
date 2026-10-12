"""Recognize problem links, guess languages, and find or create shared problem rows."""

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Problem


@dataclass(frozen=True)
class ProblemRef:
    platform: str
    slug: str
    url: str | None


_LEETCODE = re.compile(r"leetcode\.(?:com|cn)/problems/([a-z0-9-]+)", re.I)
_CODEFORCES = re.compile(
    r"codeforces\.com/(?:problemset/problem/(\d+)/([A-Z]\d?)|contest/(\d+)/problem/([A-Z]\d?))",
    re.I,
)


def parse_problem_link(link: str) -> ProblemRef:
    link = link.strip()
    if m := _LEETCODE.search(link):
        slug = m.group(1).lower()
        return ProblemRef("leetcode", slug, f"https://leetcode.com/problems/{slug}/")
    if m := _CODEFORCES.search(link):
        contest = m.group(1) or m.group(3)
        index = (m.group(2) or m.group(4)).upper()
        return ProblemRef(
            "codeforces",
            f"{contest}{index}",
            f"https://codeforces.com/problemset/problem/{contest}/{index}",
        )
    return ProblemRef("other", "link-" + _digest(link), link)


def ref_from_statement(statement: str) -> ProblemRef:
    return ProblemRef("other", "statement-" + _digest(statement.strip()), None)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


_LANGUAGE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("cpp", re.compile(r"#include\s*<|std::|vector<|class Solution\s*\{\s*public:")),
    (
        "csharp",
        re.compile(r"using System|public class Solution\s*\{[^}]*public\s+\w+\s+[A-Z]\w*\("),
    ),
    ("java", re.compile(r"public\s+(?:static\s+)?\w[\w<>\[\]]*\s+\w+\s*\(|import java\.")),
    ("python", re.compile(r"^\s*def \w+\(.*\):|^\s*class \w+(?:\(.*\))?:|self\.", re.M)),
    ("go", re.compile(r"^\s*func \w*\s*\(|^package \w+", re.M)),
    ("rust", re.compile(r"\bfn \w+\(|impl Solution|-> \w+ \{|\blet mut\b")),
    ("typescript", re.compile(r"function \w+\([^)]*:\s*\w+|:\s*number\[\]|=>\s*\w+\s*\{")),
    ("javascript", re.compile(r"\bvar \w+ = function|\bconst \w+ = \(|\bfunction \w+\(")),
    ("kotlin", re.compile(r"\bfun \w+\(")),
]


def detect_language(code: str) -> str:
    for language, pattern in _LANGUAGE_HINTS:
        if pattern.search(code):
            return language
    return "plaintext"


def fallback_title(slug: str) -> str:
    """A readable title from a slug, used until real metadata arrives."""
    return slug.replace("-", " ").title()


DIFFICULTIES = {"Easy", "Medium", "Hard"}


async def get_or_create_problem(
    session: AsyncSession,
    platform: str,
    slug: str,
    url: str | None,
    title: str | None = None,
    difficulty: str | None = None,
    topic_tags: list[str] | None = None,
    frontend_id: str | None = None,
    platform_question_id: str | None = None,
) -> Problem:
    """Problems are shared, so user-supplied metadata only fills empty fields; the server's own
    LeetCode fetch overwrites it whenever that succeeds."""
    problem = await session.scalar(
        select(Problem).where(Problem.platform == platform, Problem.slug == slug)
    )
    if problem is None:
        problem = Problem(platform=platform, slug=slug, url=url, topic_tags=[])
        session.add(problem)
    if title and not problem.title:
        problem.title = title.strip()[:300]
    if difficulty in DIFFICULTIES and not problem.difficulty:
        problem.difficulty = difficulty
    if topic_tags and not problem.topic_tags:
        problem.topic_tags = topic_tags
    if frontend_id and not problem.frontend_id:
        problem.frontend_id = frontend_id
    if platform_question_id and not problem.platform_question_id:
        problem.platform_question_id = platform_question_id
    if problem.title is None and platform == "leetcode":
        problem.title = fallback_title(slug)
    await session.flush()
    return problem
