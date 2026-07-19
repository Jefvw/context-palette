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

    def test_ci_runs_the_same_three_validation_phases_as_local_check(self) -> None:
        local = (ROOT / "check-context-palette.bat").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )
        install = (
            "python -m pip install --disable-pip-version-check "
            "-r requirements.txt"
        )
        phases = (
            "python -m context_palette.configuration_check",
            "python -m compileall -q src",
            "python -m unittest discover tests",
        )

        self.assertIn('python-version-file: ".python-version"', workflow)
        self.assertIn('$env:PYTHONPATH = "$PWD\\src"', workflow)
        self.assertIn(install, workflow)
        for local_command, ci_command in (
            ("-m context_palette.configuration_check", phases[0]),
            ("-m compileall -q src", phases[1]),
            ("-m unittest discover tests", phases[2]),
        ):
            self.assertIn(local_command, local)
            self.assertIn(ci_command, workflow)
        self.assertLess(workflow.index(install), workflow.index(phases[0]))
        self.assertLess(workflow.index(phases[0]), workflow.index(phases[1]))
        self.assertLess(workflow.index(phases[1]), workflow.index(phases[2]))
        self.assertEqual(workflow.count("if ($LASTEXITCODE -ne 0)"), 4)

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

    def test_setup_migrates_retired_local_features_before_validation(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        migration = (
            '".venv\\Scripts\\python.exe" -m '
            "context_palette.retired_feature_cleanup"
        )
        tests = '".venv\\Scripts\\python.exe" -m unittest discover tests'
        self.assertIn('set "PYTHONPATH=%CD%\\src"', script)
        self.assertIn(migration, script)
        self.assertLess(script.index(migration), script.index(tests))

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
