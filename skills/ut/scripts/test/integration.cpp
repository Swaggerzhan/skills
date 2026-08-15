#include <gtest/gtest.h>

// @UT-HEADER-BEGIN
// @Unit: MetadataServiceTest
// @Tier: integration // solitary | component | integration
// @Deps: rpc(mock), raft(inject)
// @Desc: service requests driven through the RPC boundary.
// @Args:
//   - operation identifies the supported request type
//   - expected_code is the returned service status
//
// @Category-BEGIN: Positive
//   * Branch BP1: accept every supported metadata operation.
//     * Case: accepts_supported_operation
// @Category-END: Positive
// @UT-HEADER-END

class MetadataServiceTest : public testing::TestWithParam<int> {};

const char* macro_decoy = R"(TEST_F(WrongFixture, raw_string_decoy))";

// @UT-CASE-BEGIN
// @Case: accepts_supported_operation
// @Status: done
// @Detail: dispatches each supported operation to the service implementation.
// @Setup: route RPC calls to the in-process service.
// @UT-CASE-END
TEST_P(
    MetadataServiceTest,
    accepts_supported_operation) {
    EXPECT_GE(GetParam(), 0);
}
