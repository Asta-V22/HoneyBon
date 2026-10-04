"""Fixed vocabularies the review contract and analytics depend on. Never free text."""

from enum import StrEnum


class Technique(StrEnum):
    HASHING = "hashing"
    TWO_POINTERS = "two_pointers"
    SLIDING_WINDOW = "sliding_window"
    PREFIX_SUM = "prefix_sum"
    BINARY_SEARCH = "binary_search"
    STACK = "stack"
    MONOTONIC_STACK = "monotonic_stack"
    LINKED_LIST = "linked_list"
    TREE_DFS = "tree_dfs"
    TREE_BFS = "tree_bfs"
    GRAPH_DFS = "graph_dfs"
    GRAPH_BFS = "graph_bfs"
    TOPOLOGICAL_SORT = "topological_sort"
    UNION_FIND = "union_find"
    SHORTEST_PATH = "shortest_path"
    HEAP = "heap"
    GREEDY = "greedy"
    DYNAMIC_PROGRAMMING = "dynamic_programming"
    BACKTRACKING = "backtracking"
    BIT_MANIPULATION = "bit_manipulation"
    MATH = "math"
    TRIE = "trie"
    SEGMENT_OR_FENWICK_TREE = "segment_or_fenwick_tree"
    INTERVALS_AND_SORTING = "intervals_and_sorting"
    SIMULATION = "simulation"
    BRUTE_FORCE = "brute_force"


class ComplexityClass(StrEnum):
    """Normalized growth classes, declared from best to worst so they can be ranked.

    Multi-variable bounds (e.g. O(m*n)) are normalized by treating every input size as n.
    """

    CONSTANT = "1"
    LOG_N = "log n"
    SQRT_N = "sqrt n"
    N = "n"
    N_LOG_N = "n log n"
    N_SQRT_N = "n sqrt n"
    N_SQUARED = "n^2"
    N_SQUARED_LOG_N = "n^2 log n"
    N_CUBED = "n^3"
    EXPONENTIAL = "2^n"
    FACTORIAL = "n!"

    @property
    def rank(self) -> int:
        return list(ComplexityClass).index(self)
