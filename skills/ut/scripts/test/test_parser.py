#!/usr/bin/env python3

from test_support import CliTestCase


class AnnotationParserTest(CliTestCase):
    def test_missing_header_begin_anchor_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @UT-HEADER-BEGIN\n", "")
        self.assert_invalid(self.run_text(text), "HEADER end anchor has no begin anchor")

    def test_missing_header_end_anchor_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @UT-HEADER-END\n", "")
        self.assert_invalid(self.run_text(text), "HEADER block has no end anchor")

    def test_duplicate_header_blocks_are_rejected(self):
        text = self.fixture_text("solitary.cpp") * 2
        self.assert_invalid(self.run_text(text), "expected exactly one HEADER block")

    def test_nested_header_block_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @UT-HEADER-BEGIN\n",
            "// @UT-HEADER-BEGIN\n// @UT-HEADER-BEGIN\n",
        )
        self.assert_invalid(self.run_text(text), "nested HEADER block")

    def test_header_anchor_with_trailing_text_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @UT-HEADER-BEGIN", "// @UT-HEADER-BEGIN extra"
        )
        self.assert_invalid(self.run_text(text), "must occupy its own comment line")

    def test_unmatched_case_end_anchor_is_rejected(self):
        text = "// @UT-CASE-END\n" + self.fixture_text("solitary.cpp")
        self.assert_invalid(self.run_text(text), "CASE end anchor has no begin anchor")

    def test_unclosed_case_block_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp", "// @UT-CASE-END\n", ""
        )
        self.assert_invalid(self.run_text(text), "CASE block has no end anchor")

    def test_nested_case_block_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @UT-CASE-BEGIN\n",
            "// @UT-CASE-BEGIN\n// @UT-CASE-BEGIN\n",
        )
        self.assert_invalid(self.run_text(text), "nested CASE block")

    def test_case_anchor_with_trailing_text_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @UT-CASE-BEGIN",
            "// @UT-CASE-BEGIN extra",
        )
        self.assert_invalid(self.run_text(text), "must occupy its own comment line")

    def test_case_block_inside_header_is_rejected(self):
        block = (
            "// @UT-CASE-BEGIN\n"
            "// @Case: nested_case\n"
            "// @Status: todo\n"
            "// @UT-CASE-END\n"
        )
        text = self.replace_fixture(
            "solitary.cpp", "// @UT-HEADER-END\n", block + "// @UT-HEADER-END\n"
        )
        self.assert_invalid(self.run_text(text), "CASE block cannot appear inside HEADER")

    def test_non_comment_header_content_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Desc: parsing and validation of individual values.",
            "@Desc: parsing and validation of individual values.",
        )
        self.assert_invalid(self.run_text(text), "HEADER content must use line comments")

    def test_non_comment_case_content_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @Status: done",
            "@Status: done",
        )
        self.assert_invalid(self.run_text(text), "CASE content must use line comments")

    def test_unknown_header_field_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary\n// @Owner: team"
        )
        self.assert_invalid(self.run_text(text), "unknown HEADER field '@Owner'")

    def test_duplicate_header_field_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary\n// @Tier: solitary"
        )
        self.assert_invalid(self.run_text(text), "duplicate HEADER field '@Tier'")

    def test_unknown_case_field_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @Status: done",
            "// @Status: done\n// @Owner: team",
        )
        self.assert_invalid(self.run_text(text), "unknown CASE field '@Owner'")

    def test_duplicate_case_field_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @Status: done",
            "// @Status: done\n// @Status: done",
        )
        self.assert_invalid(self.run_text(text), "duplicate CASE field '@Status'")

    def test_unknown_header_marker_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Tier: solitary", "// @Tier: solitary\n// * Unknown: value"
        )
        self.assert_invalid(self.run_text(text), "unknown HEADER marker")

    def test_unknown_case_marker_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @Status: done",
            "// @Status: done\n// * Unknown: value",
        )
        self.assert_invalid(self.run_text(text), "unknown CASE marker")

    def test_orphan_header_continuation_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "//\n// @Category-BEGIN: Positive",
            "//\n// orphan continuation\n// @Category-BEGIN: Positive",
        )
        self.assert_invalid(self.run_text(text), "orphan HEADER continuation line")

    def test_orphan_case_continuation_is_rejected(self):
        text = self.replace_fixture(
            "invalid_done_without_test.cpp",
            "// @UT-CASE-BEGIN\n// @Case:",
            "// @UT-CASE-BEGIN\n// orphan continuation\n// @Case:",
        )
        self.assert_invalid(self.run_text(text), "orphan CASE continuation line")

    def test_nested_category_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Category-BEGIN: Positive",
            "// @Category-BEGIN: Positive\n// @Category-BEGIN: Recovery",
        )
        self.assert_invalid(self.run_text(text), "nested category block")

    def test_unmatched_category_end_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Category-BEGIN: Positive",
            "// @Category-END: Recovery\n// @Category-BEGIN: Positive",
        )
        self.assert_invalid(self.run_text(text), "category end anchor has no begin anchor")

    def test_mismatched_category_end_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp", "// @Category-END: Positive", "// @Category-END: Recovery"
        )
        self.assert_invalid(self.run_text(text), "does not match 'Positive'")

    def test_unclosed_category_is_rejected(self):
        text = self.replace_fixture("solitary.cpp", "// @Category-END: Negative\n", "")
        self.assert_invalid(self.run_text(text), "category block has no end anchor")

    def test_branch_outside_category_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Category-BEGIN: Positive",
            "// * Branch BP1: outside\n// @Category-BEGIN: Positive",
        )
        self.assert_invalid(self.run_text(text), "branch must be inside a category")

    def test_case_outside_category_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "// @Category-BEGIN: Positive",
            "// * Case: outside_case\n// @Category-BEGIN: Positive",
        )
        self.assert_invalid(self.run_text(text), "case must be inside a category")

    def test_header_field_inside_category_is_rejected(self):
        text = self.replace_fixture(
            "solitary.cpp",
            "//   * Case: parses_valid_value",
            "// @Args: misplaced\n//   * Case: parses_valid_value",
        )
        self.assert_invalid(self.run_text(text), "@Args must be outside categories")
