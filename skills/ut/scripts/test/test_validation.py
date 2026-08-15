#!/usr/bin/env python3

from test_support import CliTestCase


class SemanticValidationTest(CliTestCase):
    def test_missing_unit_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @Unit: ParserLogicTest\n", "")
        self.assert_invalid(self.run_text(text), "missing required HEADER field '@Unit'")

    def test_empty_unit_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Unit: ParserLogicTest", "// @Unit:"
        )
        self.assert_invalid(self.run_text(text), "@Unit must not be empty")

    def test_invalid_unit_identifier_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Unit: ParserLogicTest", "// @Unit: Parser-Logic-Test"
        )
        self.assert_invalid(self.run_text(text), "invalid @Unit 'Parser-Logic-Test'")

    def test_missing_tier_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @Tier: solitary\n", "")
        self.assert_invalid(self.run_text(text), "missing required HEADER field '@Tier'")

    def test_empty_tier_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @Tier: solitary", "// @Tier:")
        self.assert_invalid(self.run_text(text), "@Tier must not be empty")

    def test_invalid_tier_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: sociable"
        )
        self.assert_invalid(self.run_text(text), "invalid @Tier 'sociable'")

    def test_missing_description_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Desc: parsing and validation of individual values.\n", ""
        )
        self.assert_invalid(self.run_text(text), "missing required HEADER field '@Desc'")

    def test_empty_description_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Desc: parsing and validation of individual values.",
            "// @Desc:",
        )
        self.assert_invalid(self.run_text(text), "@Desc must not be empty")

    def test_header_without_categories_is_rejected(self):
        text = (
            "#include <gtest/gtest.h>\n\n"
            "// @UT-HEADER-BEGIN\n"
            "// @Unit: EmptyTest\n"
            "// @Tier: solitary\n"
            "// @Desc: no cases have been designed.\n"
            "// @UT-HEADER-END\n"
        )
        self.assert_invalid(self.run_text(text), "HEADER must contain at least one category")

    def test_invalid_category_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "Positive", "Unexpected", count=2
        )
        self.assert_invalid(self.run_text(text), "invalid category 'Unexpected'")

    def test_duplicate_category_is_rejected(self):
        duplicate = (
            "// @Category-BEGIN: Positive\n"
            "//   * Case: (todo)\n"
            "// @Category-END: Positive\n"
        )
        text = self.replace_fixture(
            "solitary.cpp", "// @UT-HEADER-END\n", duplicate + "// @UT-HEADER-END\n"
        )
        self.assert_invalid(self.run_text(text), "duplicate category 'Positive'")

    def test_empty_category_is_rejected(self):
        empty_category = (
            "// @Category-BEGIN: Recovery\n"
            "// @Category-END: Recovery\n"
        )
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Category-BEGIN: Positive",
            empty_category + "// @Category-BEGIN: Positive",
        )
        self.assert_invalid(self.run_text(text), "category 'Recovery' has no cases")

    def test_solitary_branch_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "//   * Case: parses_valid_value",
            "//   * Branch BP1: unnecessary branch.\n"
            "//     * Case: parses_valid_value",
        )
        self.assert_invalid(self.run_text(text), "solitary tests cannot contain branches")

    def test_solitary_dependencies_are_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary\n// @Deps: rpc(mock)"
        )
        self.assert_invalid(self.run_text(text), "solitary tests must omit @Deps")

    def test_component_without_dependencies_is_rejected(self):
        text = self.replace_fixture(
            "component.cpp", "// @Deps: store(mock), clock(inject)\n", ""
        )
        self.assert_invalid(self.run_text(text), "component tests require @Deps")

    def test_component_with_empty_dependencies_is_rejected(self):
        text = self.replace_fixture(
            "component.cpp", "// @Deps: store(mock), clock(inject)", "// @Deps:"
        )
        self.assert_invalid(self.run_text(text), "@Deps must not be empty")

    def test_malformed_dependency_is_rejected(self):
        text = self.replace_fixture(
            "component.cpp",
            "// @Deps: store(mock), clock(inject)",
            "// @Deps: store mock",
        )
        self.assert_invalid(self.run_text(text), "invalid dependency 'store mock'")

    def test_trailing_dependency_separator_is_rejected(self):
        text = self.replace_fixture(
            "component.cpp",
            "// @Deps: store(mock), clock(inject)",
            "// @Deps: store(mock),",
        )
        self.assert_invalid(self.run_text(text), "invalid dependency ''")

    def test_wrong_branch_prefix_is_rejected(self):
        text = self.replace_fixture("integration.cpp", "Branch BP1", "Branch BN1")
        self.assert_invalid(self.run_text(text), "must use prefix 'BP'")

    def test_zero_branch_number_is_rejected(self):
        text = self.replace_fixture("integration.cpp", "Branch BP1", "Branch BP0")
        self.assert_invalid(self.run_text(text), "must use prefix 'BP'")

    def test_duplicate_branch_id_is_rejected(self):
        duplicate = (
            "//   * Branch BP1: duplicate branch id.\n"
            "//     * Case: (todo)\n"
        )
        text = self.replace_fixture(
            "component.cpp", "// @Category-END: Positive", duplicate + "// @Category-END: Positive"
        )
        self.assert_invalid(self.run_text(text), "duplicate branch id 'BP1'")

    def test_empty_branch_description_is_rejected(self):
        text = self.replace_fixture(
            "integration.cpp",
            "//   * Branch BP1: accept every supported metadata operation.",
            "//   * Branch BP1:",
        )
        self.assert_invalid(self.run_text(text), "branch 'BP1' must have a description")

    def test_branch_without_cases_is_rejected(self):
        text = self.replace_fixture(
            "integration.cpp", "//     * Case: accepts_supported_operation\n", ""
        )
        self.assert_invalid(self.run_text(text), "branch 'BP1' has no cases")

    def test_invalid_header_case_name_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "//   * Case: parses_valid_value", "//   * Case: invalid-name"
        )
        self.assert_invalid(self.run_text(text), "invalid case name 'invalid-name'")

    def test_duplicate_header_case_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "//   * Case: parses_valid_value",
            "//   * Case: parses_valid_value\n//   * Case: parses_valid_value",
        )
        self.assert_invalid(self.run_text(text), "duplicate HEADER case 'parses_valid_value'")

    def test_case_block_missing_case_field_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp", "// @Case: marked_done_without_body\n", ""
        )
        self.assert_invalid(self.run_text(text), "CASE block is missing '@Case'")

    def test_empty_case_field_is_rejected(self):
        text = self.replace_fixture(
            "component.cpp", "// @Case: refreshes_expired_value", "// @Case:"
        )
        self.assert_invalid(self.run_text(text), "@Case must not be empty")

    def test_case_block_missing_status_is_rejected(self):
        text = self.replace_fixture("component.cpp", "// @Status: todo\n", "")
        self.assert_invalid(self.run_text(text), "CASE block is missing '@Status'")

    def test_empty_status_is_rejected(self):
        text = self.replace_fixture("component.cpp", "// @Status: todo", "// @Status:")
        self.assert_invalid(self.run_text(text), "@Status must not be empty")

    def test_duplicate_case_block_is_rejected(self):
        duplicate = (
            "\n// @UT-CASE-BEGIN\n"
            "// @Case: rejects_empty_value\n"
            "// @Status: todo\n"
            "// @UT-CASE-END\n"
        )
        text = self.fixture_text("solitary.cpp") + duplicate
        self.assert_invalid(self.run_text(text), "duplicate CASE block for 'rejects_empty_value'")

    def test_unregistered_case_block_is_rejected(self):
        orphan = (
            "\n// @UT-CASE-BEGIN\n"
            "// @Case: orphan_case\n"
            "// @Status: todo\n"
            "// @UT-CASE-END\n"
        )
        text = self.fixture_text("solitary.cpp") + orphan
        self.assert_invalid(self.run_text(text), "CASE 'orphan_case' is not registered in HEADER")

    def test_solitary_setup_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Status: todo",
            "// @Status: todo\n// @Setup: no dependency is allowed.",
        )
        self.assert_invalid(self.run_text(text), "solitary CASE blocks must omit @Setup")

    def test_include_after_header_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @UT-HEADER-END\n", "// @UT-HEADER-END\n#include <vector>\n"
        )
        self.assert_invalid(self.run_text(text), "all includes must appear before HEADER")
