"""Interpolated regex fragments must be atomic units.

A fragment with a top-level ``A|B`` alternation, once interpolated into
``prefix + fragment``, becomes ``prefix + A | B``. Wrapping the constant
in ``(?:...)`` (or a capturing group) keeps both alternatives bound to
the prefix. This file guards that class of bug.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import rasta.extract


def _walk_regex_chars(pattern: str):
    """Yield (index, char, paren_depth, in_class) for unescaped pattern chars."""
    depth = 0
    in_class = False
    escaped = False
    class_start: int | None = None
    for index, char in enumerate(pattern):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if in_class:
            # The first char of a class (or the first after ^) may be a
            # literal ], but after that ] ends the class.
            if char == "]" and index != class_start:
                in_class = False
                class_start = None
            yield index, char, depth, True
            continue
        if char == "[":
            in_class = True
            class_start = index + 1
            if index + 1 < len(pattern) and pattern[index + 1] == "^":
                class_start = index + 2
            yield index, char, depth, True
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        yield index, char, depth, False


def has_top_level_alternation(pattern: str) -> bool:
    """True if ``|`` appears at parenthesis depth 0, outside a character class."""
    return any(
        char == "|" and depth == 0 and not in_class
        for _index, char, depth, in_class in _walk_regex_chars(pattern)
    )


def is_single_wrapping_group(pattern: str) -> bool:
    """True if the whole pattern is one group, so it interpolates as a unit."""
    if len(pattern) < 2 or pattern[0] != "(":
        return False
    close_at = None
    for index, char, depth, in_class in _walk_regex_chars(pattern):
        if not in_class and char == ")" and depth == 0:
            close_at = index
            break
    return close_at == len(pattern) - 1


def interpolated_fragment_names(source: str) -> frozenset[str]:
    """Names interpolated into f-strings / rf-strings in ``source``."""
    names: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for value in node.values:
            if isinstance(value, ast.FormattedValue) and isinstance(
                value.value, ast.Name
            ):
                names.add(value.value.id)
    return frozenset(names)


def unsafe_interpolated_fragments(module: ModuleType) -> tuple[str, ...]:
    """Fragment constants that have an ungrouped top-level ``|``."""
    path = Path(module.__file__).resolve()
    names = interpolated_fragment_names(path.read_text(encoding="utf-8"))
    unsafe: list[str] = []
    for name in sorted(names):
        value = getattr(module, name, None)
        if not isinstance(value, str):
            continue
        if has_top_level_alternation(value):
            unsafe.append(name)
    return tuple(unsafe)


def test_interpolated_regex_fragments_are_self_grouped():
    unsafe = unsafe_interpolated_fragments(rasta.extract)
    assert unsafe == (), (
        "interpolated regex fragments have an ungrouped top-level '|': "
        f"{unsafe}. Wrap each constant in (?:...) so interpolation cannot "
        "change precedence."
    )


def test_ungrouped_alternation_detector_catches_the_baat_hui_shape():
    # The exact class of bug in _BAAT_OK before it was grouped.
    bare = r"baat\s+ho\s+(?:gayi|gai)|baat\s+hui"
    grouped = r"(?:baat\s+ho\s+(?:gayi|gai)|baat\s+hui)"
    assert has_top_level_alternation(bare)
    assert not is_single_wrapping_group(bare)
    # After wrapping, the pipe sits inside the group, so the fragment is
    # an atomic unit under interpolation.
    assert not has_top_level_alternation(grouped)
    assert is_single_wrapping_group(grouped)
    already = r"(?:phone|mobile|call)"
    assert not has_top_level_alternation(already)
    assert is_single_wrapping_group(already)
    # A trailing quantifier means the wrapping group is not the whole
    # string, but there is still no top-level pipe.
    quantified = r"(?:foo|bar){0,3}"
    assert not has_top_level_alternation(quantified)
    assert not is_single_wrapping_group(quantified)
