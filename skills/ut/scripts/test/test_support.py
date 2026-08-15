import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
CLI = TEST_DIR.parent / "cli.py"
_CLI_MODULE = None


def load_cli_module():
    global _CLI_MODULE
    if _CLI_MODULE is not None:
        return _CLI_MODULE
    spec = importlib.util.spec_from_file_location("ut_cli", CLI)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CLI}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _CLI_MODULE = module
    return module


class CliTestCase(unittest.TestCase):
    maxDiff = None

    def fixture_text(self, fixture):
        return (TEST_DIR / fixture).read_text(encoding="utf-8")

    def replace_fixture(self, fixture, old, new, count=1):
        text = self.fixture_text(fixture)
        self.assertGreaterEqual(text.count(old), count)
        return text.replace(old, new, count)

    def command(self, arguments):
        return [sys.executable, str(CLI), *arguments]

    def run_arguments(self, arguments):
        if os.environ.get("UT_IN_PROCESS") == "1":
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    returncode = load_cli_module().main(arguments)
            except SystemExit as error:
                returncode = error.code if isinstance(error.code, int) else 1
            return subprocess.CompletedProcess(
                self.command(arguments), returncode, stdout.getvalue(), stderr.getvalue()
            )
        return subprocess.run(
            self.command(arguments), text=True, capture_output=True, check=False
        )

    def run_path(self, path, operation, case_name=None):
        arguments = ["--file", str(path), "--op", operation]
        if case_name is not None:
            arguments.extend(["--case_name", case_name])
        return self.run_arguments(arguments)

    def run_cli(self, fixture, operation, case_name=None):
        return self.run_path(TEST_DIR / fixture, operation, case_name)

    def run_text(self, text, operation="verify", case_name=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.cpp"
            path.write_text(text, encoding="utf-8")
            return self.run_path(path, operation, case_name)

    def run_bytes(self, content, operation="verify"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.cpp"
            path.write_bytes(content)
            return self.run_path(path, operation)

    def assert_invalid(self, result, message):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)
