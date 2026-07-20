from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceTransform:
    """User-facing metadata for one constrained workspace transformation."""

    label: str
    operation: str
    success_message: str
    prompts_for_affixes: bool = False


@dataclass(frozen=True, slots=True)
class WorkspaceTransformGroup:
    label: str
    transforms: tuple[WorkspaceTransform, ...]


WORKSPACE_TRANSFORM_GROUPS = (
    WorkspaceTransformGroup(
        "Case",
        (
            WorkspaceTransform("lowercase", "lowercase", "lowercase"),
            WorkspaceTransform("UPPERCASE", "uppercase", "UPPERCASE"),
            WorkspaceTransform("Proper Case", "proper_case", "Applied Proper Case"),
            WorkspaceTransform("Sentence case", "sentence_case", "Applied sentence case"),
            WorkspaceTransform("iNVERT cASE", "invert_case", "Inverted case"),
        ),
    ),
    WorkspaceTransformGroup(
        "Whitespace",
        (
            WorkspaceTransform(
                "Normalize consecutive spaces",
                "normalize_spaces",
                "Normalized spaces",
            ),
            WorkspaceTransform("Trim every line", "trim_lines", "Trimmed every line"),
        ),
    ),
    WorkspaceTransformGroup(
        "Lines",
        (
            WorkspaceTransform(
                "Prefix / suffix every line…",
                "prefix_suffix_lines",
                "Added line prefix and suffix",
                prompts_for_affixes=True,
            ),
            WorkspaceTransform(
                "Remove blank lines",
                "remove_blank_lines",
                "Removed blank lines",
            ),
            WorkspaceTransform(
                "Sort lines A–Z",
                "sort_lines_ascending",
                "Sorted lines A–Z",
            ),
            WorkspaceTransform(
                "Sort lines Z–A",
                "sort_lines_descending",
                "Sorted lines Z–A",
            ),
            WorkspaceTransform("Join lines with spaces", "join_lines", "Joined lines"),
            WorkspaceTransform(
                "Format as SQL value list",
                "sql_values",
                "Formatted SQL value list",
            ),
            WorkspaceTransform(
                "Remove consecutive duplicate lines",
                "remove_consecutive_duplicate_lines",
                "Removed consecutive duplicate lines",
            ),
            WorkspaceTransform(
                "Remove duplicate lines",
                "remove_duplicate_lines",
                "Removed duplicate lines",
            ),
        ),
    ),
)
