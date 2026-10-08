"""Optional static capability discovery; never inventory or attach to Excel."""
from pathlib import Path
from uuid import uuid4

from .excel_automation import (
    DescribeCapabilitiesResult, ExcelAutomationCoordinator, ExcelAutomationSettingsError,
    LIVE_NATIVE_TEXT_OPERATION, build_describe_capabilities_request,
    discover_direct_sibling_python_excel_launcher, load_excel_automation_settings,
)


class NativeExcelAvailability:
    """Cache exact engine metadata outside F9 and outside the Tk thread."""

    def __init__(self, settings_path, installation_root, *, on_changed, coordinator=None):
        self.settings_path = Path(settings_path)
        self.installation_root = Path(installation_root)
        self.on_changed = on_changed
        self.coordinator = coordinator or ExcelAutomationCoordinator()
        self.available = False
        self._generation = 0
        self._launcher = None
        self._queued = False

    @property
    def busy(self):
        return self.coordinator.running or self.coordinator.completion_pending

    def refresh(self):
        self._generation += 1
        self.available = False
        self._launcher = None
        try:
            settings = load_excel_automation_settings(self.settings_path)
            launcher = settings.launcher_path
            if launcher is None:
                launcher = discover_direct_sibling_python_excel_launcher(self.installation_root)
            if launcher is not None and launcher.is_file():
                self._launcher = launcher
        except (ExcelAutomationSettingsError, OSError):
            pass
        self.on_changed()
        self._queued = self._launcher is not None
        self._start_queued()

    def _start_queued(self):
        if not self._queued or self.busy:
            return
        generation, launcher = self._generation, self._launcher
        self._queued = False
        self.coordinator.start(launcher, build_describe_capabilities_request(f"native-catalogue-{uuid4().hex}"),
                               phase="capabilities", timeout_seconds=15,
                               on_complete=lambda call: self._completed(generation, call))

    def _completed(self, generation, call):
        if generation != self._generation:
            return
        result = call.result
        self.available = (
            call.classification == "capabilities_succeeded" and isinstance(result, DescribeCapabilitiesResult)
            and all((capability := result.find(operation, "1.0")) is not None
                    and capability.availability.available
                    for operation in ("inventory_live_excel", "preflight_live_columns", LIVE_NATIVE_TEXT_OPERATION))
        )
        self.on_changed()

    def drain(self):
        self.coordinator.drain()
        self._start_queued()
