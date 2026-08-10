from __future__ import annotations

from dataclasses import dataclass

from .work_items import WorkItemReference


class PaletteItemReferenceError(ValueError):
    """A persisted reference does not identify exactly one Palette item."""


@dataclass(frozen=True)
class PaletteItemReference:
    """Stable reference to one invokable Action or Work Item."""

    action_id: str = ""
    work_item_ref: WorkItemReference | None = None

    def __post_init__(self) -> None:
        clean_action_id = self.action_id.strip()
        if bool(clean_action_id) == bool(self.work_item_ref):
            raise PaletteItemReferenceError(
                "A Palette-item reference must contain exactly one Action or Work Item."
            )
        object.__setattr__(self, "action_id", clean_action_id)

    @property
    def kind(self) -> str:
        return "action" if self.action_id else "work_item"

    @property
    def stable_key(self) -> str:
        if self.action_id:
            return f"action:{self.action_id}"
        assert self.work_item_ref is not None
        return (
            f"work_item:{self.work_item_ref.source_id}/"
            f"{self.work_item_ref.relative_folder}"
        )


def palette_item_reference_data(
    reference: PaletteItemReference,
) -> dict[str, str]:
    if reference.action_id:
        return {"type": "action", "action_id": reference.action_id}
    assert reference.work_item_ref is not None
    return {
        "type": "work_item",
        "source_id": reference.work_item_ref.source_id,
        "relative_folder": reference.work_item_ref.relative_folder,
    }
