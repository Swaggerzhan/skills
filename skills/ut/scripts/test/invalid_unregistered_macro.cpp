#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: UnregisteredMacroTest
// @Tier: solitary
// @Desc: fixture with a test macro that the HEADER does not register.
//
// @Category-BEGIN: Positive
//   * Case: registered_case
// @Category-END: Positive
// @UT-HEADER-END

class UnregisteredMacroTest : public testing::Test {};

TEST_F(UnregisteredMacroTest, phantom_case) {
    EXPECT_TRUE(true);
}
