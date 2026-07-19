from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsScriptTests(unittest.TestCase):
    def test_setup_uses_tracked_version_and_preserves_an_unusable_environment(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        health_check = "expected_prefix=pathlib.Path('.venv').resolve()"
        preserve = 'move ".venv" "!VENV_BACKUP!"'
        create = "!PYTHON_CMD! -m venv .venv"

        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.12")
        self.assertIn('set /p "PYTHON_VERSION="<".python-version"', script)
        self.assertIn("expected_version=os.environ['PYTHON_VERSION']", script)
        self.assertIn("marker_matches=not marker.exists()", script)
        self.assertIn('> ".venv\\.context-palette-root" echo %CD%', script)
        self.assertIn(health_check, script)
        self.assertIn(preserve, script)
        self.assertIn(create, script)
        self.assertLess(script.index(health_check), script.index(preserve))
        self.assertLess(script.index(preserve), script.index(create))

    def test_setup_checks_real_interpreters_in_fallback_order(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        preferred = 'py -!PYTHON_VERSION! -c "import sys, tkinter"'
        path_fallback = 'python -c "import os, sys, tkinter;'

        self.assertLess(script.index(preferred), script.index(path_fallback))
        self.assertIn("EnableDelayedExpansion", script)
        self.assertIn("!PYTHON_CMD! -m venv .venv", script)

    def test_development_entry_point_repairs_then_runs_canonical_check(self) -> None:
        script = (ROOT / "develop-context-palette.bat").read_text(encoding="utf-8")

        setup = "call setup-context-palette.bat --skip-tests"
        check = "call check-context-palette.bat"
        self.assertIn('cd /d "%~dp0"', script)
        self.assertLess(script.index(setup), script.index(check))

    def test_setup_reinstalls_dependencies_only_when_requirements_change(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        calculate = "hashlib.sha256(pathlib.Path('requirements.txt').read_bytes())"
        install = (
            '".venv\\Scripts\\python.exe" -m pip install '
            "--disable-pip-version-check -r requirements.txt"
        )
        record = '> "!REQUIREMENTS_MARKER!" echo !REQUIREMENTS_HASH!'
        self.assertIn(".context-palette-requirements.sha256", script)
        self.assertIn(calculate, script)
        self.assertIn(install, script)
        self.assertIn(record, script)
        self.assertLess(script.index(install), script.index(record))

    def test_launcher_rejects_a_missing_or_unusable_environment(self) -> None:
        script = (ROOT / "run-context-palette.bat").read_text(encoding="utf-8")

        self.assertIn('if not exist ".venv\\Scripts\\python.exe"', script)
        self.assertIn(
            '".venv\\Scripts\\python.exe" -c "import sys, tkinter"', script
        )
        self.assertIn("Run setup-context-palette.bat to repair it.", script)

    def test_project_python_wrapper_sets_source_path_and_checks_environment(self) -> None:
        script = (ROOT / "python-context-palette.bat").read_text(encoding="utf-8")

        self.assertIn('cd /d "%~dp0"', script)
        self.assertIn('set "PYTHONPATH=%CD%\\src;%PYTHONPATH%"', script)
        environment_check = '".venv\\Scripts\\python.exe" -c "import sys, tkinter"'
        project_check = '".venv\\Scripts\\python.exe" -c "import context_palette"'
        self.assertIn(environment_check, script)
        self.assertIn(project_check, script)
        self.assertLess(script.index(environment_check), script.index(project_check))
        self.assertIn("Run setup-context-palette.bat to repair it.", script)
        self.assertIn(
            "Run check-context-palette.bat and review the error above.", script
        )
        self.assertIn('".venv\\Scripts\\python.exe" %*', script)
        self.assertIn("exit /b %errorlevel%", script)


if __name__ == "__main__":
    unittest.main()
