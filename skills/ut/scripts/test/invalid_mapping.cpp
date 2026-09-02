#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: ExpectedFixtureTest
// @Tier: solitary
// @Desc: fixture whose test macro uses the wrong unit.
//
// @Category-BEGIN: Positive
//   * Case: mapped_case
// @Category-END: Positive
// @UT-HEADER-END

class ExpectedFixtureTest : public testing::Test {};

TEST_F(OtherFixtureTest, mapped_case) {
    EXPECT_TRUE(true);
}
