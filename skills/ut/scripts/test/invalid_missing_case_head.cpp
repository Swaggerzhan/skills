#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: MissingCaseHeadTest
// @Tier: solitary
// @Desc: fixture with a missing CASE block.
//
// @Category-BEGIN: Positive
//   * Case: declared_only_in_header
// @Category-END: Positive
// @UT-HEADER-END

class MissingCaseHeadTest : public testing::Test {};
