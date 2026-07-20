from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_DIRECTORIES = (ROOT / "docs", ROOT / "integrations")
LINK_PATTERN = re.compile(
    r"!?\[[^\]]*\]\("
    r"(?P<target><[^>]+>|[^)\s]+)"
    r"(?:\s+[\"'][^\"']*[\"'])?"
    r"\)"
)
EXTERNAL_TARGET_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def documentation_files() -> list[Path]:
    files = list(ROOT.glob("*.md"))
    for directory in DOCUMENTATION_DIRECTORIES:
        if directory.exists():
            files.extend(directory.rglob("*.md"))
    return sorted(set(files))


def markdown_links(path: Path) -> list[tuple[int, str]]:
    links: list[tuple[int, str]] = []
    fence: str | None = None
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.lstrip()
        fence_match = re.match(r"(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        line_without_inline_code = re.sub(r"`[^`]*`", "", line)
        links.extend(
            (line_number, match.group("target").strip("<>"))
            for match in LINK_PATTERN.finditer(line_without_inline_code)
        )
    return links


def local_link_target(source: Path, target: str) -> Path | None:
    if (
        not target
        or target.startswith("#")
        or target.startswith("//")
        or EXTERNAL_TARGET_PATTERN.match(target)
    ):
        return None
    path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not path_text:
        return None
    if path_text.startswith("/"):
        return (ROOT / path_text.lstrip("/")).resolve()
    return (source.parent / Path(path_text)).resolve()


def has_exact_repository_case(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    current = ROOT
    for part in relative.parts:
        matching_names = {child.name for child in current.iterdir()}
        if part not in matching_names:
            return False
        current /= part
    return True


class DocumentationLinkTests(unittest.TestCase):
    def test_internal_markdown_links_resolve_with_exact_case(self):
        broken: list[str] = []
        for source in documentation_files():
            for line_number, target in markdown_links(source):
                destination = local_link_target(source, target)
                if destination is None:
                    continue
                if not destination.exists():
                    reason = "target does not exist"
                elif not has_exact_repository_case(destination):
                    reason = "target casing does not match the repository"
                else:
                    continue
                source_name = source.relative_to(ROOT)
                broken.append(
                    f"{source_name}:{line_number}: {target} ({reason})"
                )

        self.assertEqual(
            broken,
            [],
            "Broken internal Markdown links:\n" + "\n".join(broken),
        )

    def test_link_extraction_ignores_examples_and_external_targets(self):
        fixture = ROOT / "tests" / "_markdown_link_fixture.md"
        content = (
            "[local](../README.md)\n"
            "[web](https://example.com/page)\n"
            "[heading](#section)\n"
            "`[inline](missing.md)`\n"
            "```text\n"
            "[example](missing.md)\n"
            "```\n"
        )
        try:
            fixture.write_text(content, encoding="utf-8")
            links = markdown_links(fixture)
        finally:
            fixture.unlink(missing_ok=True)

        self.assertEqual(
            links,
            [
                (1, "../README.md"),
                (2, "https://example.com/page"),
                (3, "#section"),
            ],
        )
        self.assertEqual(
            local_link_target(fixture, links[0][1]),
            ROOT / "README.md",
        )
        self.assertIsNone(local_link_target(fixture, links[1][1]))
        self.assertIsNone(local_link_target(fixture, links[2][1]))


if __name__ == "__main__":
    unittest.main()
