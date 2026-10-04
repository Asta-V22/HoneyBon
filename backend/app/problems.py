"""Recognize problem links and guess languages for pasted submissions."""

import hashlib
import re
from dataclasses import dataclass


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
