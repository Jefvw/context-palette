import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsScriptTests(unittest.TestCase):
    def test_setup_uses_tracked_version_and_preserves_an_unusable_environment(self) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        health_check = "expected_prefix=pathlib.Path('.venv').resolve()"
        compatible_python_check = "call :find_compatible_python"
        safe_stop_route = "goto :venv_check_unavailable"
        safe_stop = "The environment was not renamed or rebuilt."
        preserve = 'move ".venv" "!VENV_BACKUP!"'
        create = "!PYTHON_CMD! -m venv .venv"

        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.12")
        self.assertIn('set /p "PYTHON_VERSION="<".python-version"', script)
        self.assertIn("expected_version=os.environ['PYTHON_VERSION']", script)
        self.assertIn("marker_matches=not marker.exists()", script)
        self.assertIn('> ".venv\\.context-palette-root" echo %CD%', script)
        self.assertIn(health_check, script)
        self.assertIn(compatible_python_check, script)
        self.assertIn("CONTEXT_PALETTE_PYTHON", script)
        self.assertIn(
            r"!LocalAppData!\Programs\Python\Python!PYTHON_MAJOR!!PYTHON_MINOR!\python.exe",
            script,
        )
        self.assertIn(
            r"!ProgramFiles!\Python!PYTHON_MAJOR!!PYTHON_MINOR!\python.exe",
            script,
        )
        self.assertNotIn("call :try_python_executable", script)
        self.assertIn(safe_stop, script)
        self.assertIn(preserve, script)
        self.assertIn(create, script)
        self.assertLess(script.index(health_check), script.index(compatible_python_check))
        self.assertLess(
            script.index(compatible_python_check),
            script.index(safe_stop_route),
        )
        self.assertLess(script.index(safe_stop_route), script.index(preserve))
        self.assertIn(safe_stop, script)
        self.assertLess(script.index(preserve), script.index(create))

    def test_setup_does_not_move_venv_when_no_base_python_can_validate_repair(
        self,
    ) -> None:
        script = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")

        repair_route = ":repair_existing_venv"
        independent_check = "call :find_compatible_python"
        guard = "if not defined PYTHON_CMD goto :venv_check_unavailable"
        safe_stop = "The environment was not renamed or rebuilt."
        preserve = 'move ".venv" "!VENV_BACKUP!"'

        health_block = script[
            script.index(repair_route):script.index(preserve)
        ]
        self.assertIn(independent_check, health_block)
        self.assertIn(guard, health_block)
        self.assertIn(safe_stop, script)
        self.assertIn("retry with normal Windows access", script)

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_setup_preserves_failed_venv_when_python_is_inaccessible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            fake_python = root / ".venv" / "Scripts" / "python.exe"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_bytes(b"not a Windows executable")
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["LOCALAPPDATA"] = str(root / "missing-local-app-data")
            environment["PROGRAMFILES"] = str(root / "missing-program-files")
            environment["PROGRAMFILES(X86)"] = str(
                root / "missing-program-files-x86"
            )

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-context-palette.bat",
                    "--skip-tests",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn(
                "The environment was not renamed or rebuilt.",
                result.stdout,
            )
            self.assertTrue(fake_python.exists())
            self.assertEqual(list(root.glob(".venv-unusable*")), [])

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_development_wrapper_preserves_venv_when_python_is_inaccessible(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for filename in (
                "develop-context-palette.bat",
                "setup-context-palette.bat",
            ):
                (root / filename).write_text(
                    (ROOT / filename).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            fake_python = root / ".venv" / "Scripts" / "python.exe"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_bytes(b"not a Windows executable")
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["LOCALAPPDATA"] = str(root / "missing-local-app-data")
            environment["PROGRAMFILES"] = str(root / "missing-program-files")
            environment["PROGRAMFILES(X86)"] = str(
                root / "missing-program-files-x86"
            )

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "develop-context-palette.bat",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn(
                "The environment was not renamed or rebuilt.",
                result.stdout,
            )
            self.assertTrue(fake_python.exists())
            self.assertEqual(list(root.glob(".venv-unusable*")), [])

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_fresh_setup_without_python_reports_failure_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["LOCALAPPDATA"] = str(root / "missing-local-app-data")
            environment["PROGRAMFILES"] = str(root / "missing-program-files")
            environment["PROGRAMFILES(X86)"] = str(
                root / "missing-program-files-x86"
            )

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-context-palette.bat",
                    "--skip-tests",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn(
                "A usable Python 3.12 installation was not found.",
                result.stdout,
            )
            self.assertFalse((root / ".venv").exists())
            self.assertEqual(list(root.glob(".venv-unusable*")), [])

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_fresh_setup_accepts_an_explicit_compatible_python_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["CONTEXT_PALETTE_PYTHON"] = sys._base_executable

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-context-palette.bat",
                    "--skip-tests",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertNotIn(
                "A usable Python 3.12 installation was not found.",
                result.stdout,
            )
            self.assertIn(
                "Creating local Python 3.12 environment...",
                result.stdout,
            )
            self.assertTrue((root / ".venv" / "Scripts" / "python.exe").exists())

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_fresh_setup_finds_the_standard_per_user_python_without_path(
        self,
    ) -> None:
        standard_python = (
            Path(os.environ["LOCALAPPDATA"])
            / "Programs"
            / "Python"
            / "Python312"
            / "python.exe"
        )
        if not standard_python.exists():
            self.skipTest("Python 3.12 is not installed in the per-user location")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment.pop("CONTEXT_PALETTE_PYTHON", None)

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-context-palette.bat",
                    "--skip-tests",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertNotIn(
                "A usable Python 3.12 installation was not found.",
                result.stdout,
            )
            self.assertIn(
                "Creating local Python 3.12 environment...",
                result.stdout,
            )
            self.assertTrue((root / ".venv" / "Scripts" / "python.exe").exists())

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_setup_moves_failed_venv_only_after_base_python_is_confirmed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            fake_python = root / ".venv" / "Scripts" / "python.exe"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_bytes(b"not a Windows executable")
            environment = os.environ.copy()
            environment["PATH"] = str(Path(sys.executable).parent)

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-context-palette.bat",
                    "--skip-tests",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "Preserved the old environment as .venv-unusable.",
                result.stdout,
            )
            self.assertTrue(
                (
                    root
                    / ".venv-unusable"
                    / "Scripts"
                    / "python.exe"
                ).exists()
            )

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
