"""Technique analytics: the approach-avoidance matrix, the tag cross-check and the insight card.

Pure functions over one row per problem (the latest analysed submission), so they are easy to
test. Rows of the matrix are the technique the problem needed, columns the one the user reached
for. Using any technique in a problem's optimal set is a match: BFS where DFS is equally optimal
is not flagged.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.reviews.taxonomy import ComplexityClass, Technique

T = Technique

# LeetCode topic-tag slugs -> techniques that tag implies. Tags that say nothing about the
# approach ("array", "string", "matrix", "design") are left out.
TAG_TECHNIQUES: dict[str, set[Technique]] = {
    "hash-table": {T.HASHING},
    "counting": {T.HASHING},
    "two-pointers": {T.TWO_POINTERS},
    "sliding-window": {T.SLIDING_WINDOW},
    "monotonic-queue": {T.SLIDING_WINDOW, T.MONOTONIC_STACK},
    "prefix-sum": {T.PREFIX_SUM},
    "binary-search": {T.BINARY_SEARCH},
    "stack": {T.STACK, T.MONOTONIC_STACK},
    "monotonic-stack": {T.MONOTONIC_STACK},
    "linked-list": {T.LINKED_LIST, T.TWO_POINTERS},
    "doubly-linked-list": {T.LINKED_LIST},
    "tree": {T.TREE_DFS, T.TREE_BFS},
    "binary-tree": {T.TREE_DFS, T.TREE_BFS},
    "binary-search-tree": {T.TREE_DFS, T.TREE_BFS, T.BINARY_SEARCH},
    "depth-first-search": {T.TREE_DFS, T.GRAPH_DFS, T.BACKTRACKING},
    "breadth-first-search": {T.TREE_BFS, T.GRAPH_BFS, T.SHORTEST_PATH},
    "graph": {T.GRAPH_DFS, T.GRAPH_BFS, T.SHORTEST_PATH, T.TOPOLOGICAL_SORT, T.UNION_FIND},
    "topological-sort": {T.TOPOLOGICAL_SORT},
    "union-find": {T.UNION_FIND},
    "shortest-path": {T.SHORTEST_PATH},
    "heap-priority-queue": {T.HEAP},
    "greedy": {T.GREEDY},
    "dynamic-programming": {T.DYNAMIC_PROGRAMMING},
    "memoization": {T.DYNAMIC_PROGRAMMING},
    "backtracking": {T.BACKTRACKING},
    "recursion": {T.BACKTRACKING, T.TREE_DFS},
    "bit-manipulation": {T.BIT_MANIPULATION},
    "bitmask": {T.BIT_MANIPULATION, T.DYNAMIC_PROGRAMMING},
    "math": {T.MATH},
    "number-theory": {T.MATH},
    "combinatorics": {T.MATH},
    "geometry": {T.MATH},
    "trie": {T.TRIE},
    "segment-tree": {T.SEGMENT_OR_FENWICK_TREE},
    "binary-indexed-tree": {T.SEGMENT_OR_FENWICK_TREE},
    "sorting": {T.INTERVALS_AND_SORTING},
    "line-sweep": {T.INTERVALS_AND_SORTING},
    "simulation": {T.SIMULATION},
    "database": {
        T.SQL_FILTERING,
        T.SQL_JOINS,
        T.SQL_AGGREGATION,
        T.SQL_SUBQUERIES_CTES,
        T.SQL_WINDOW_FUNCTIONS,
        T.SQL_SORTING_LIMITING,
    },
}

_ORDER = {t.value: i for i, t in enumerate(Technique)}


def _rank(value: str | None) -> int | None:
    try:
        return ComplexityClass(value).rank if value else None
    except ValueError:
        return None


def tag_techniques(tags: list[str]) -> set[str]:
    return {t.value for tag in tags for t in TAG_TECHNIQUES.get(tag, ())}


@dataclass(frozen=True)
class ProblemRow:
    """The latest analysed submission of one problem."""

    submission_id: str
    title: str
    difficulty: str | None
    platform: str
    used: str
    optimal: list[str]
    time_class: str | None
    space_class: str | None
    optimal_time_class: str | None
    optimal_space_class: str | None
    topic_tags: list[str] = field(default_factory=list)

    @property
    def match(self) -> bool:
        return self.used in self.optimal

    @property
    def worse(self) -> bool:
        """A worse time or space class than the optimum: a real weakness, not a style choice."""
        pairs = [
            (self.time_class, self.optimal_time_class),
            (self.space_class, self.optimal_space_class),
        ]
        for actual, best in pairs:
            a, b = _rank(actual), _rank(best)
            if a is not None and b is not None and a > b:
                return True
        return False

    @property
    def needed(self) -> str:
        """The matrix row: the technique used when it matched, else the most standard optimum."""
        return self.used if self.match else self.optimal[0]

    @property
    def low_confidence(self) -> bool | None:
        """True when LeetCode's tags imply techniques and none of them is in the AI's optimal
        set. None when there are no informative tags to check against."""
        implied = tag_techniques(self.topic_tags)
        if not implied:
            return None
        return not (implied & set(self.optimal))


@dataclass(frozen=True)
class InsightCard:
    technique: str  # the technique avoided
    avoided: int  # problems where it was optimal and something else was used
    worse: int  # of those, how many ended in a worse complexity
    out_of: int  # problems where it was optimal
    usual_instead: str  # what the user reached for most often instead
    submission_ids: list[str]


def strongest_avoidance(rows: list[ProblemRow], min_problems: int) -> InsightCard | None:
    """The single technique the user most often avoids where it was optimal.

    Low-confidence problems (the AI disagrees with LeetCode's tags) are left out, and nothing is
    claimed until the pattern rests on at least `min_problems` problems.
    """
    trusted = [r for r in rows if r.low_confidence is not True]
    avoided: dict[str, list[ProblemRow]] = defaultdict(list)
    optimal_in: Counter[str] = Counter()
    for r in trusted:
        for t in r.optimal:
            optimal_in[t] += 1
        if not r.match:
            for t in r.optimal:
                avoided[t].append(r)
    candidates = [
        (sum(r.worse for r in rs), len(rs), -_ORDER.get(t, 99), t)
        for t, rs in avoided.items()
        if len(rs) >= min_problems
    ]
    if not candidates:
        return None
    worse, count, _, technique = max(candidates)
    problems = avoided[technique]
    usual = Counter(r.used for r in problems).most_common(1)[0][0]
    return InsightCard(
        technique=technique,
        avoided=count,
        worse=worse,
        out_of=optimal_in[technique],
        usual_instead=usual,
        submission_ids=[r.submission_id for r in problems],
    )


@dataclass(frozen=True)
class Cell:
    needed: str
    used: str
    count: int
    worse: int


def matrix(rows: list[ProblemRow]) -> tuple[list[str], list[str], list[Cell]]:
    """(row techniques, column techniques, non-empty cells), both axes in taxonomy order."""
    cells: dict[tuple[str, str], list[ProblemRow]] = defaultdict(list)
    for r in rows:
        cells[(r.needed, r.used)].append(r)
    needed = sorted({k[0] for k in cells}, key=lambda t: _ORDER.get(t, 99))
    used = sorted({k[1] for k in cells}, key=lambda t: _ORDER.get(t, 99))
    return (
        needed,
        used,
        [
            Cell(needed=n, used=u, count=len(rs), worse=sum(r.worse for r in rs))
            for (n, u), rs in cells.items()
        ],
    )
