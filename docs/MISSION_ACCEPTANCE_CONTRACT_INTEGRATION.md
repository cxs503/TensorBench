# TensorPlatform Mission Acceptance Contract Integration

TensorBench collects the Mission's acceptance criteria together with the immutable SHA-256, freeze timestamp, version, and freeze provenance.

The collector verifies the digest against the canonical JSON representation. It does not treat a digest as proof that a criterion was achieved.

## Trust rules

- `mission_created` + a matching digest + non-empty criteria: contract integrity is verified and provenance is predeclared.
- `legacy_start`: digest integrity may be verified, but the criteria were only frozen when work started; the evaluator remains inconclusive on contract provenance.
- Missing criteria, missing digest, invalid data, or `legacy_unfrozen`: not a passing contract.
- Digest mismatch: fail closed.

Platform criteria use `metric`, `target`, and `tolerance`. TensorBench maps these to its evaluator's statement field while preserving the original fields. It does not infer criterion-to-test relationships from generic green CI checks. Without explicit test IDs and revision-pinned run evidence, criterion achievement remains inconclusive.

A SHA-256 match proves only that the collected criteria match the frozen snapshot. It does not prove scientific validity, correctness, or achievement.
