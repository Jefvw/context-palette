from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceTransform:
    """User-facing metadata for one constrained workspace transformation."""

    label: str
    operation: str
    success_message: str
    parameter_labels: tuple[str, ...] = ()
    parameter_defaults: tuple[str, ...] = ()

    @property
    def prompts_for_affixes(self) -> bool:
        """Retain the old semantic helper for callers and compatibility tests."""
        return self.operation == "prefix_suffix_lines"

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
            WorkspaceTransform(
                "Collapse multiple blank lines",
                "collapse_blank_lines",
                "Collapsed multiple blank lines",
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "Find and filter",
        (
            WorkspaceTransform(
                "Find and replace…",
                "literal_replace",
                "Replaced matching text",
                ("Find", "Replace with"),
            ),
            WorkspaceTransform(
                "Keep lines containing…",
                "keep_lines_containing",
                "Kept matching lines",
                ("Text to find (case-insensitive)",),
            ),
            WorkspaceTransform(
                "Remove lines containing…",
                "remove_lines_containing",
                "Removed matching lines",
                ("Text to find (case-insensitive)",),
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "Paths",
        (
            WorkspaceTransform(
                "Forward slashes / to backslashes \\",
                "forward_to_back",
                "Changed / to \\",
            ),
            WorkspaceTransform(
                "Backslashes \\ to forward slashes /",
                "back_to_forward",
                "Changed \\ to /",
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "Lines",
        (
            WorkspaceTransform(
                "Prefix / suffix every line…",
                "prefix_suffix_lines",
                "Added line prefix and suffix",
                ("Prefix for every line", "Suffix for every line"),
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
                "Split using a delimiter…",
                "split_delimiter",
                "Split text into lines",
                ("Delimiter (use \\t for a tab)",),
                (",",),
            ),
            WorkspaceTransform(
                "Join using a delimiter…",
                "join_delimiter",
                "Joined lines",
                ("Delimiter (use \\t for a tab)",),
                (", ",),
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
    WorkspaceTransformGroup(
        "Lists",
        (
            WorkspaceTransform(
                "Comma list: no quotes",
                "comma_list_plain",
                "Created comma list without quotes",
            ),
            WorkspaceTransform(
                "Comma list: single-quoted text",
                "comma_list_single_quotes",
                "Created comma list with single-quoted text",
            ),
            WorkspaceTransform(
                "Comma list: double-quoted text",
                "comma_list_double_quotes",
                "Created comma list with double-quoted text",
            ),
            WorkspaceTransform(
                "Parenthesized SQL value list",
                "sql_values",
                "Formatted SQL value list",
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "Naming style",
        (
            WorkspaceTransform("camelCase", "camel_case", "Converted to camelCase"),
            WorkspaceTransform("PascalCase", "pascal_case", "Converted to PascalCase"),
            WorkspaceTransform("snake_case", "snake_case", "Converted to snake_case"),
            WorkspaceTransform(
                "SCREAMING_SNAKE_CASE",
                "screaming_snake_case",
                "Converted to SCREAMING_SNAKE_CASE",
            ),
            WorkspaceTransform("kebab-case", "kebab_case", "Converted to kebab-case"),
            WorkspaceTransform(
                "Readable words",
                "readable_words",
                "Converted identifiers to readable words",
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "Data and encoding",
        (
            WorkspaceTransform("Pretty-print JSON", "json_pretty", "Formatted JSON"),
            WorkspaceTransform("Minify JSON", "json_minify", "Minified JSON"),
            WorkspaceTransform("URL-encode text", "url_encode", "URL-encoded text"),
            WorkspaceTransform("URL-decode text", "url_decode", "URL-decoded text"),
            WorkspaceTransform(
                "Escape SQL single quotes",
                "sql_escape_quotes",
                "Escaped SQL single quotes",
            ),
        ),
    ),
    WorkspaceTransformGroup(
        "File addresses",
        (
            WorkspaceTransform(
                "Windows path to file: URI",
                "path_to_file_uri",
                "Converted path to file URI",
            ),
            WorkspaceTransform(
                "file: URI to Windows path",
                "file_uri_to_path",
                "Converted file URI to Windows path",
            ),
        ),
    ),
)


WORKSPACE_TRANSFORMS = {
    transform.operation: transform
    for group in WORKSPACE_TRANSFORM_GROUPS
    for transform in group.transforms
}
