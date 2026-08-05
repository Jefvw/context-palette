from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from .configuration_snapshot import load_configuration_snapshot
from .data_catalog import AppDataPaths


@dataclass(frozen=True)
class ConfigurationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    counts: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_project_configuration(root: Path) -> ConfigurationReport:
    snapshot_report = load_configuration_snapshot(AppDataPaths.from_root(root))
    return ConfigurationReport(
        tuple(issue.summary for issue in snapshot_report.errors),
        tuple(issue.summary for issue in snapshot_report.warnings),
        dict(snapshot_report.counts),
    )


def format_configuration_report(report: ConfigurationReport) -> str:
    lines = ["Context Palette configuration check", "==================================="]
    for name, count in sorted(report.counts.items()):
        lines.append(f"{name.replace('_', ' ').title()}: {count}")
    if report.warnings:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("\nErrors:")
        lines.extend(f"- {error}" for error in report.errors)
    else:
        lines.append("\nConfiguration is valid.")
    return "\n".join(lines)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    report = validate_project_configuration(root)
    print(format_configuration_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
