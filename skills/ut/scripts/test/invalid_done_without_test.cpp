#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: DoneWithoutTest
// @Tier: solitary
// @Desc: fixture with a done case that has no test macro.
//
// @Category-BEGIN: Positive
//   * Case: marked_done_without_body
// @Category-END: Positive
// @UT-HEADER-END

class DoneWithoutTest : public testing::Test {};

// @UT-CASE-BEGIN
// @Case: marked_done_without_body
// @Status: done
// @UT-CASE-END
