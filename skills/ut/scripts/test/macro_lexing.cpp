#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: MacroLexingTest
// @Tier: solitary
// @Desc: recognition of real test macros without lexical decoys.
//
// @Category-BEGIN: Positive
//   * Case: detects_real_macro
// @Category-END: Positive
// @UT-HEADER-END

class MacroLexingTest : public testing::Test {};

// TEST_F(WrongFixture, line_comment_decoy) {
// }

/* TEST_F(WrongFixture, block_comment_decoy) {
} */

const char* string_decoy = "TEST_F(WrongFixture, string_decoy)";
const char* escaped_string_decoy = "quoted: \"TEST_F(WrongFixture, escaped_decoy)\"";
const char* raw_string_decoy = R"tag(TEST_F(WrongFixture, raw_decoy))tag";
const char macro_character = 'T';

// @Detail: ignores comments and string literals while finding the real macro.
TEST_F /* macro comments are legal whitespace */ (
    MacroLexingTest /* fixture comment */,
    detects_real_macro) {
    EXPECT_EQ(macro_character, 'T');
}
