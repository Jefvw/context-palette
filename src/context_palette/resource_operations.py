"""Runtime-only requests shared by resource entry points and effect adapters.

Requests snapshot input, not permission. Callers retain Action validation and
Drop approval; adapters retain domain review, execution and recovery. A dispatch
receipt describes hand-off, never completion of an asynchronous operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .actions import (
    Action, ActionError, EXCEL_AUTOMATION_IDS,
)
from .excel_automation import EXCEL_AUTOMATION_ID
from .webpage_pdf import WebpagePdfError, validate_webpage_url


Invocation = Literal["manual", "drop"]


@dataclass(frozen=True, slots=True)
class FolderResource:
    """A destination projected from an Action, Work Item or folder picker."""

    key: str
    label: str
    folder_path: Path
    menu_path: tuple[str, ...] = ()
    search_text: str = ""


@dataclass(frozen=True, slots=True)
class OpenTargetRequest:
    action: Action  # Already expanded by the canonical Action executor.


@dataclass(frozen=True, slots=True)
class CopyFilesRequest:
    destination: FolderResource
    input_text: str
    invocation: Invocation = "manual"


@dataclass(frozen=True, slots=True)
class ExcelWorkflowRequest:
    action: Action
    input_text: str | None = None
    invocation: Invocation = "manual"
    source_window_handle: int | None = None


@dataclass(frozen=True, slots=True)
class WebpagePdfRequest:
    input_text: str
    destination_path: Path
    invocation: Invocation = "manual"


@dataclass(frozen=True, slots=True)
class EdgeScorePdfRequest:
    source_window_handle: int
    destination_folder: Path
    invocation: Invocation = "manual"


ResourceOperationRequest = (
    OpenTargetRequest | CopyFilesRequest | ExcelWorkflowRequest | WebpagePdfRequest
    | EdgeScorePdfRequest
)


@dataclass(frozen=True, slots=True)
class OperationDispatch:
    status: Literal["opened", "workflow_started"]
    message: str


def dispatch_resource_operation(
    request: ResourceOperationRequest,
    *,
    open_target: Callable[[Action], None],
    copy_files: Callable[[CopyFilesRequest], str],
    excel_workflow: Callable[[ExcelWorkflowRequest], str],
    webpage_pdf: Callable[[WebpagePdfRequest], str] | None = None,
    edge_score_pdf: Callable[[EdgeScorePdfRequest], str] | None = None,
) -> OperationDispatch:
    """Route exactly one operation; do not acquire input or bypass its review."""
    if isinstance(request, OpenTargetRequest):
        if request.action.type not in {
            "open_url", "open_file", "open_folder", "open_windows_target", "launch_app",
        }:
            raise ActionError("The requested Action is not an open-target operation.")
        open_target(request.action)
        return OperationDispatch("opened", "Asked the target handler to open the resource.")
    if isinstance(request, EdgeScorePdfRequest):
        if request.invocation != "manual":
            raise ActionError("Run the score PDF Action manually from Context Palette.")
        if (
            type(request.source_window_handle) is not int
            or request.source_window_handle <= 0
            or not isinstance(request.destination_folder, Path)
            or not request.destination_folder.is_absolute()
        ):
            raise ActionError("Choose an Edge window and an absolute score PDF folder.")
        if edge_score_pdf is None:
            raise ActionError("Edge score PDF saving is unavailable here.")
        return OperationDispatch("workflow_started", edge_score_pdf(request))
    if isinstance(request, WebpagePdfRequest):
        if request.invocation != "manual":
            raise ActionError("Save a webpage as PDF from Input / Output's Send to menu.")
        try:
            validate_webpage_url(request.input_text)
        except WebpagePdfError as exc:
            raise ActionError(str(exc)) from exc
        if webpage_pdf is None:
            raise ActionError("Webpage PDF creation is unavailable here.")
        return OperationDispatch("workflow_started", webpage_pdf(request))
    if not isinstance(request, (CopyFilesRequest, ExcelWorkflowRequest)):
        raise ActionError("Unsupported resource operation request.")
    if request.invocation not in {"manual", "drop"}:
        raise ActionError("Unsupported resource invocation source.")
    if isinstance(request, CopyFilesRequest):
        if not isinstance(request.input_text, str) or not request.input_text.strip():
            raise ActionError("Paste or drop one or more file paths before choosing Send to.")
        return OperationDispatch("workflow_started", copy_files(request))
    if request.action.type != "excel_automation" or request.action.value not in EXCEL_AUTOMATION_IDS:
        raise ActionError("The selected Excel automation is unsupported.")
    if request.action.value == EXCEL_AUTOMATION_ID:
        if not isinstance(request.input_text, str):
            raise ActionError("Excel CSV export requires an Input / Output snapshot.")
    elif request.invocation != "manual" or request.input_text is not None:
        raise ActionError("Live Excel Actions choose open workbooks; run them from the Palette.")
    if request.invocation == "drop" and request.source_window_handle is not None:
        raise ActionError("Dropped input cannot identify a captured Excel window.")
    return OperationDispatch("workflow_started", excel_workflow(request))
