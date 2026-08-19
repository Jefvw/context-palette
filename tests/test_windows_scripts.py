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
        self.assertIn(
            "minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.')))",
            script,
        )
        self.assertIn("import os, pathlib, pip, sys, tkinter", script)
        self.assertIn("actual[0] == minimum[0] and actual >= minimum", script)
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
                timeout=15,
                check=False,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn(
                "A usable Python 3.12 or newer 3.x installation was not found.",
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
                "A usable Python 3.12 or newer 3.x installation was not found.",
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
        compatibility = subprocess.run(
            [standard_python, "-c", "import pip, tkinter"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if compatibility.returncode:
            self.skipTest(
                "Per-user Python 3.12 does not provide both pip and Tkinter"
            )

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
                "A usable Python 3.12 or newer 3.x installation was not found.",
                result.stdout,
            )
            self.assertIn(
                "Creating local Python 3.12 environment...",
                result.stdout,
            )
            self.assertTrue((root / ".venv" / "Scripts" / "python.exe").exists())

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_setup_rebuilds_an_existing_environment_without_pip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-context-palette.bat").write_text(
                (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".python-version").write_text("3.12\n", encoding="utf-8")
            subprocess.run(
                [
                    sys._base_executable,
                    "-m",
                    "venv",
                    "--without-pip",
                    str(root / ".venv"),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
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
                timeout=45,
                check=False,
            )

            self.assertIn(
                "Preserved the old environment as .venv-unusable.",
                result.stdout,
            )
            self.assertTrue(
                (root / ".venv-unusable" / "Scripts" / "python.exe").exists()
            )
            pip_check = subprocess.run(
                [
                    root / ".venv" / "Scripts" / "python.exe",
                    "-c",
                    "import pip",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                pip_check.returncode,
                0,
                msg=f"stdout:\n{pip_check.stdout}\nstderr:\n{pip_check.stderr}",
            )

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

        preferred = 'py -!PYTHON_VERSION! -c "import pip, sys, tkinter"'
        path_fallback = 'python -c "import os, pip, sys, tkinter;'

        self.assertLess(script.index(preferred), script.index(path_fallback))
        self.assertIn("EnableDelayedExpansion", script)
        self.assertIn("!PYTHON_CMD! -m venv .venv", script)

    def test_development_entry_point_repairs_then_runs_canonical_check(self) -> None:
        script = (ROOT / "develop-context-palette.bat").read_text(encoding="utf-8")

        setup = "call setup-context-palette.bat --skip-tests"
        check = "call check-context-palette.bat"
        self.assertIn('cd /d "%~dp0"', script)
        self.assertLess(script.index(setup), script.index(check))

    def test_optional_ocr_setup_stays_local_and_uses_pinned_requirements(self) -> None:
        script = (ROOT / "setup-ocr-context-palette.bat").read_text(
            encoding="utf-8"
        )
        requirements = (ROOT / "requirements-ocr.txt").read_text(encoding="utf-8")

        self.assertIn("rapidocr==3.9.2", requirements)
        self.assertIn("onnxruntime==1.27.0", requirements)
        self.assertIn("call setup-context-palette.bat --skip-tests", script)
        self.assertIn('".venv\\Scripts\\python.exe" -m pip install', script)
        self.assertIn("-r requirements-ocr.txt", script)
        self.assertIn(".context-palette-ocr-requirements.sha256", script)
        self.assertIn("OCR dependencies are unchanged", script)
        self.assertIn("does not require administrator rights", script)
        self.assertIn("Core Context Palette setup completed", script)
        self.assertIn("remains available", script)
        self.assertIn("Only Extract text is unavailable", script)
        self.assertNotIn("runas", script.casefold())

    def test_setup_supports_a_strict_offline_package_folder(self) -> None:
        base = (ROOT / "setup-context-palette.bat").read_text(encoding="utf-8")
        ocr = (ROOT / "setup-ocr-context-palette.bat").read_text(
            encoding="utf-8"
        )

        for script in (base, ocr):
            self.assertIn("CONTEXT_PALETTE_WHEELHOUSE", script)
            self.assertIn("--no-index", script)
            self.assertIn("--find-links", script)
        self.assertIn("offline package folder does not exist", base)

    def test_offline_helpers_prepare_and_consume_all_pinned_dependencies(self) -> None:
        prepare = (ROOT / "prepare-offline-context-palette.bat").read_text(
            encoding="utf-8"
        )
        setup = (ROOT / "setup-offline-context-palette.bat").read_text(
            encoding="utf-8"
        )
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        core_setup = "call setup-context-palette.bat --skip-tests"
        core_wheels = '-m pip wheel --disable-pip-version-check --wheel-dir "offline-packages" -r requirements.txt'
        ocr_wheels = '-m pip wheel --disable-pip-version-check --wheel-dir "offline-packages" -r requirements-ocr.txt'
        self.assertIn(core_setup, prepare)
        self.assertNotIn("call setup-ocr-context-palette.bat", prepare)
        self.assertLess(prepare.index(core_setup), prepare.index(core_wheels))
        self.assertLess(prepare.index(core_wheels), prepare.index(ocr_wheels))
        self.assertIn("target PC can still install and run Context Palette", prepare)
        self.assertIn('set "CONTEXT_PALETTE_WHEELHOUSE=', setup)
        self.assertIn(core_setup, setup)
        self.assertIn("call setup-ocr-context-palette.bat", setup)
        self.assertIn("call check-context-palette.bat", setup)
        self.assertLess(setup.index(core_setup), setup.index("call setup-ocr-context-palette.bat"))
        self.assertLess(setup.index("call setup-ocr-context-palette.bat"), setup.index("call check-context-palette.bat"))
        self.assertIn("Core offline setup and checks are complete", setup)
        self.assertIn("only Extract text is unavailable", setup)
        self.assertIn("/offline-packages/", ignore)

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_offline_setup_finishes_core_when_optional_ocr_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "setup-offline-context-palette.bat").write_text(
                (ROOT / "setup-offline-context-palette.bat").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            (root / "offline-packages").mkdir()
            for filename, label, return_code in (
                ("setup-context-palette.bat", "core", 0),
                ("setup-ocr-context-palette.bat", "ocr", 1),
                ("check-context-palette.bat", "check", 0),
            ):
                (root / filename).write_text(
                    "@echo off\n"
                    f"echo {label}>>order.txt\n"
                    f"exit /b {return_code}\n",
                    encoding="utf-8",
                )

            result = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "setup-offline-context-palette.bat",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertEqual(
                (root / "order.txt").read_text(encoding="utf-8").splitlines(),
                ["core", "ocr", "check"],
            )
            self.assertIn("Core offline setup and checks are complete", result.stdout)
            self.assertIn("only Extract text is unavailable", result.stdout)

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

    def test_ui_mockup_launcher_is_inert_and_uses_pythonw(self) -> None:
        script = (ROOT / "run-ui-mockups.bat").read_text(encoding="utf-8")

        self.assertIn('set "PYTHONPATH=%CD%\\src"', script)
        self.assertIn("import sys, tkinter, context_palette.ui_mockups", script)
        self.assertIn(
            'start "" ".\\.venv\\Scripts\\pythonw.exe" -m context_palette.ui_mockups',
            script,
        )
        self.assertNotIn("context_palette.main", script)


if __name__ == "__main__":
    unittest.main()
