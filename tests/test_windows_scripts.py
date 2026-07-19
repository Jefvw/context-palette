from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsScriptTests(unittest.TestCase):
    def test_setup_detects_and_preserves_an_unusable_environment(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        health_check = '".venv\\Scripts\\python.exe" -c "import sys, tkinter"'
        preserve = 'move ".venv" ".venv-unusable"'
        create = "!PYTHON_CMD! -m venv .venv"

        self.assertIn(health_check, script)
        self.assertIn(preserve, script)
        self.assertIn(create, script)
        self.assertLess(script.index(health_check), script.index(preserve))
        self.assertLess(script.index(preserve), script.index(create))

    def test_setup_checks_real_interpreters_in_fallback_order(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        preferred = 'py -3.12 -c "import sys, tkinter"'
        launcher_fallback = 'py -3 -c "import sys, tkinter; raise SystemExit'
        path_fallback = 'python -c "import sys, tkinter; raise SystemExit'

        self.assertLess(script.index(preferred), script.index(launcher_fallback))
        self.assertLess(script.index(launcher_fallback), script.index(path_fallback))
        self.assertIn("EnableDelayedExpansion", script)
        self.assertIn("!PYTHON_CMD! -m venv .venv", script)

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
