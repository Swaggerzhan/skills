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
            "solitary.cpp", "// @Tier: solitary", "// @Tier: unit"
        )
        self.assert_invalid(self.run_text(text), "invalid @Tier 'unit'")

    def test_tier_accepts_inline_comment(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary // the tier"
        )
        result = self.run_text(text)
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_solitary_may_use_branches(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "//   * Case: parses_valid_value",
            "//   * Branch BP1: parsing of individual values.\n"
            "//     * Case: parses_valid_value",
        )
        result = self.run_text(text)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_solitary_may_declare_dependencies(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary\n// @Deps: clock(inject)"
        )
        result = self.run_text(text)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sociable_may_omit_dependencies(self):
        text = self.replace_fixture(
            "sociable.cpp", "// @Deps: store(mock), clock(inject)\n", ""
        )
        result = self.run_text(text)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_cases_and_branches_may_mix(self):
        text = self.replace_fixture(
            "sociable.cpp",
            "// @Category-END: Positive",
            "//   * Case: handles_empty_cache\n// @Category-END: Positive",
        )
        result = self.run_text(text)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_dependencies_are_rejected(self):
        text = self.replace_fixture(
            "sociable.cpp", "// @Deps: store(mock), clock(inject)", "// @Deps:"
        )
        self.assert_invalid(self.run_text(text), "@Deps must not be empty")

    def test_malformed_dependency_is_rejected(self):
        text = self.replace_fixture(
            "sociable.cpp",
            "// @Deps: store(mock), clock(inject)",
            "// @Deps: store mock",
        )
        self.assert_invalid(self.run_text(text), "invalid dependency 'store mock'")

    def test_trailing_dependency_separator_is_rejected(self):
        text = self.replace_fixture(
            "sociable.cpp",
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
            "sociable.cpp", "// @Category-END: Positive", duplicate + "// @Category-END: Positive"
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

    def test_implemented_case_must_not_keep_detail_in_header(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "TEST_F(ParserLogicTest, parses_valid_value)",
            "TEST_F(ParserLogicTest, rejects_empty_value)",
        )
        self.assert_invalid(
            self.run_text(text),
            "implemented case 'rejects_empty_value' must not keep detail in the HEADER",
        )

    def test_include_after_header_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @UT-HEADER-END\n", "// @UT-HEADER-END\n#include <vector>\n"
        )
        self.assert_invalid(self.run_text(text), "all includes must appear before HEADER")
