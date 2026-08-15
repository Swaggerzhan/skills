#!/usr/bin/env python3

import json

from test_support import CLI, TEST_DIR, CliTestCase


class MacroMappingTest(CliTestCase):
    def test_macro_scanner_ignores_comment_and_string_decoys(self):
        result = self.run_cli("macro_lexing.cpp", "verify")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "OK\n")

    def test_macro_scanner_accepts_comments_and_newlines_in_signature(self):
        result = self.run_cli("macro_lexing.cpp", "case", "detects_real_macro")

        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertEqual(
            case["test"],
            {
                "type": "TEST_F",
                "unit": "MacroLexingTest",
                "case": "detects_real_macro",
            },
        )

    def test_todo_case_with_test_macro_is_rejected(self):
        macro = (
            "\nTEST_F(CacheServiceTest, refreshes_expired_value) {\n"
            "    EXPECT_TRUE(true);\n"
            "}\n"
        )
        text = self.fixture_text("component.cpp") + macro
        self.assert_invalid(self.run_text(text), "todo CASE 'refreshes_expired_value' already has")

    def test_test_macro_without_case_block_is_rejected(self):
        macro = (
            "\nTEST_F(ParserLogicTest, orphan_macro) {\n"
            "    EXPECT_TRUE(true);\n"
            "}\n"
        )
        text = self.fixture_text("solitary.cpp") + macro
        self.assert_invalid(self.run_text(text), "TEST_F case 'orphan_macro' has no CASE block")

    def test_duplicate_test_macros_are_rejected(self):
        macro = (
            "\nTEST_F(ParserLogicTest, parses_valid_value) {\n"
            "    EXPECT_TRUE(true);\n"
            "}\n"
        )
        text = self.fixture_text("solitary.cpp") + macro
        self.assert_invalid(self.run_text(text), "multiple test macros implement 'parses_valid_value'")

    def test_done_case_not_directly_above_macro_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @UT-CASE-END\nTEST_F(ParserLogicTest, parses_valid_value)",
            "// @UT-CASE-END\nint separator = 0;\nTEST_F(ParserLogicTest, parses_valid_value)",
        )
        self.assert_invalid(self.run_text(text), "must sit directly above its test macro")

    def test_macro_case_name_mismatch_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "TEST_F(ParserLogicTest, parses_valid_value)",
            "TEST_F(ParserLogicTest, different_case)",
        )
        self.assert_invalid(self.run_text(text), "TEST_F case 'different_case' has no CASE block")

    def test_macro_before_header_is_rejected(self):
        macro = "TEST_F(ParserLogicTest, early_macro) {}\n"
        text = macro + self.fixture_text("solitary.cpp")
        self.assert_invalid(self.run_text(text), "HEADER must appear before all test macros")

    def test_case_block_before_header_is_rejected(self):
        block = (
            "// @UT-CASE-BEGIN\n"
            "// @Case: early_case\n"
            "// @Status: todo\n"
            "// @UT-CASE-END\n"
        )
        text = block + self.fixture_text("solitary.cpp")
        self.assert_invalid(self.run_text(text), "CASE blocks must appear after HEADER")


class OutputContractTest(CliTestCase):
    def test_invalid_summary_emits_no_partial_json(self):
        result = self.run_cli("invalid_status.cpp", "summary")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr, "")

    def test_invalid_case_query_emits_no_partial_json(self):
        result = self.run_cli("invalid_mapping.cpp", "case", "mapped_case")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr, "")

    def test_integration_summary_reports_args_and_complete_schema(self):
        result = self.run_cli("integration.cpp", "summary")

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["unit"], "MetadataServiceTest")
        self.assertEqual(summary["tier"], "integration")
        self.assertEqual(
            summary["args"],
            [
                "operation identifies the supported request type",
                "expected_code is the returned service status",
            ],
        )
        self.assertEqual(summary["categories"][0]["name"], "Positive")
        self.assertEqual(summary["categories"][0]["branches"][0]["status"], "done")

    def test_solitary_case_has_null_branch_and_setup(self):
        result = self.run_cli("solitary.cpp", "case", "parses_valid_value")

        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertIsNone(case["branch"])
        self.assertIsNone(case["setup"])
        self.assertEqual(case["category"], "Positive")

    def test_optional_case_fields_are_null_when_omitted(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Detail: verifies that a valid value is accepted.\n", ""
        )
        result = self.run_text(text, "case", "parses_valid_value")

        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertIsNone(case["detail"])
        self.assertIsNone(case["setup"])

    def test_summary_output_is_deterministic(self):
        first = self.run_cli("component.cpp", "summary")
        second = self.run_cli("component.cpp", "summary")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_placeholder_cannot_be_queried_as_a_named_case(self):
        result = self.run_cli("solitary.cpp", "case", "(todo)")

        self.assertEqual(result.returncode, 2)
        self.assertIn("was not found", result.stderr)

    def test_successful_verify_has_no_stderr(self):
        result = self.run_cli("component.cpp", "verify")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "OK\n")
        self.assertEqual(result.stderr, "")

    def test_diagnostic_contains_path_and_line(self):
        result = self.run_cli("invalid_status.cpp", "verify")

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid_status.cpp:", result.stderr)
        self.assertRegex(result.stderr, r"invalid_status\.cpp:\d+: invalid @Status")


class ArgumentAndFileErrorTest(CliTestCase):
    def test_case_name_is_rejected_for_summary(self):
        result = self.run_arguments(
            [
                "--file",
                str(TEST_DIR / "solitary.cpp"),
                "--op",
                "summary",
                "--case_name",
                "parses_valid_value",
            ]
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("only valid for --op case", result.stderr)

    def test_case_name_is_rejected_for_verify(self):
        result = self.run_arguments(
            [
                "--file",
                str(TEST_DIR / "solitary.cpp"),
                "--op",
                "verify",
                "--case_name",
                "parses_valid_value",
            ]
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("only valid for --op case", result.stderr)

    def test_missing_file_argument_is_rejected(self):
        result = self.run_arguments(["--op", "verify"])

        self.assertEqual(result.returncode, 2)
        self.assertIn("--file", result.stderr)

    def test_missing_operation_argument_is_rejected(self):
        result = self.run_arguments(["--file", str(TEST_DIR / "solitary.cpp")])

        self.assertEqual(result.returncode, 2)
        self.assertIn("--op", result.stderr)

    def test_invalid_operation_is_rejected(self):
        result = self.run_arguments(
            ["--file", str(TEST_DIR / "solitary.cpp"), "--op", "unknown"]
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_unexpected_argument_is_rejected(self):
        result = self.run_arguments(
            ["--file", str(TEST_DIR / "solitary.cpp"), "--op", "verify", "extra"]
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_missing_file_returns_io_error(self):
        result = self.run_path(TEST_DIR / "does_not_exist.cpp", "verify")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("No such file", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_directory_path_returns_io_error(self):
        result = self.run_path(TEST_DIR, "verify")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_utf8_returns_io_error(self):
        result = self.run_bytes(b"\xff\xfe\x00")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_help_lists_all_operations(self):
        result = self.run_arguments(["--help"])

        self.assertEqual(result.returncode, 0)
        self.assertIn("summary", result.stdout)
        self.assertIn("case", result.stdout)
        self.assertIn("verify", result.stdout)
        self.assertIn("--case_name", result.stdout)

    def test_cli_path_exists(self):
        self.assertTrue(CLI.is_file())
