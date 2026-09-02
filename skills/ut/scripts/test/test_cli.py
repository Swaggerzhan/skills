#!/usr/bin/env python3

import json
import unittest

from test_support import CliTestCase


class CliTest(CliTestCase):
    def test_solitary_summary_reports_direct_case_status(self):
        result = self.run_cli("solitary.cpp", "summary")

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["tier"], "solitary")
        self.assertEqual(summary["dependencies"], [])
        self.assertEqual(
            summary["categories"][0],
            {
                "name": "Positive",
                "cases": [
                    {
                        "name": "parses_valid_value",
                        "placeholder": False,
                        "status": "done",
                    }
                ],
                "branches": [],
            },
        )
        negative_cases = summary["categories"][1]["cases"]
        self.assertEqual(negative_cases[0]["name"], "rejects_empty_value")
        self.assertEqual(negative_cases[0]["status"], "todo")
        self.assertEqual(negative_cases[1]["name"], None)
        self.assertEqual(negative_cases[1]["status"], "todo")

    def test_sociable_summary_rolls_up_branch_status(self):
        result = self.run_cli("sociable.cpp", "summary")

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(
            summary["dependencies"],
            [
                {"name": "store", "type": "mock"},
                {"name": "clock", "type": "inject"},
            ],
        )
        branches = {
            branch["id"]: branch
            for category in summary["categories"]
            for branch in category["branches"]
        }
        self.assertEqual(branches["BP1"]["status"], "partial")
        self.assertEqual(branches["BR1"]["status"], "done")
        self.assertEqual(branches["BN1"]["status"], "todo")
        self.assertEqual(
            branches["BP1"]["description"],
            "serve a cached value or refresh it when its lifetime has expired.",
        )

    def test_case_reports_multiline_detail_setup_and_macro(self):
        result = self.run_cli(
            "sociable.cpp", "case", "retries_transient_store_failure"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertEqual(case["category"], "Recovery")
        self.assertEqual(case["branch"]["id"], "BR1")
        self.assertEqual(case["status"], "done")
        self.assertEqual(
            case["detail"],
            [
                "fail the first backing-store request with a transient error",
                "verify that the retry succeeds and returns the requested value",
            ],
        )
        self.assertEqual(
            case["setup"],
            [
                "configure the store mock to fail once and then return a value",
                "inject a stable clock value",
            ],
        )
        self.assertEqual(case["test"]["type"], "TEST_F")

    def test_todo_case_reads_design_notes_from_header(self):
        result = self.run_cli("sociable.cpp", "case", "refreshes_expired_value")

        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertEqual(case["status"], "todo")
        self.assertIsNone(case["test"])
        self.assertIsNone(case["setup"])
        self.assertEqual(
            case["detail"], ["replaces an expired value from the backing store"]
        )

    def test_parameterized_case_is_supported(self):
        verify_result = self.run_cli("integration.cpp", "verify")
        case_result = self.run_cli(
            "integration.cpp", "case", "accepts_supported_operation"
        )

        self.assertEqual(verify_result.returncode, 0, verify_result.stderr)
        self.assertEqual(verify_result.stdout, "OK\n")
        self.assertEqual(case_result.returncode, 0, case_result.stderr)
        case = json.loads(case_result.stdout)
        self.assertEqual(case["test"]["type"], "TEST_P")
        self.assertEqual(case["test"]["unit"], "MetadataServiceTest")

    def test_unregistered_test_macro_is_rejected(self):
        result = self.run_cli("invalid_unregistered_macro.cpp", "verify")

        self.assertEqual(result.returncode, 1)
        self.assertIn("is not registered in HEADER", result.stderr)

    def test_invalid_dependency_type_is_rejected(self):
        result = self.run_cli("invalid_dependency.cpp", "verify")

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid dependency type 'real'", result.stderr)

    def test_wrong_test_fixture_is_rejected(self):
        result = self.run_cli("invalid_mapping.cpp", "verify")

        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match @Unit", result.stderr)

    def test_unknown_case_returns_usage_error(self):
        result = self.run_cli("solitary.cpp", "case", "unknown_case")

        self.assertEqual(result.returncode, 2)
        self.assertIn("was not found", result.stderr)

    def test_case_operation_requires_case_name(self):
        result = self.run_cli("solitary.cpp", "case")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--case_name is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
