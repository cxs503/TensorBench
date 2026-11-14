# Live Mission Evidence Collection

The live collector performs read-only GET requests to TensorPlatform and GitHub.

## Environment

- `TENSORPLATFORM_API_BASE`: API root including any deployment prefix (for example `https://platform.example/api`).
- `TENSORPLATFORM_TOKEN`: bearer token authorized to read the Mission in its tenant.
- `GITHUB_TOKEN`: optional for public repositories; required for private repositories and higher API limits.

## Command

```bash
tensorbench collect-mission --mission-id 123 --output mission-123.evidence.json
```

Optional `--github-owner` defaults to `cxs503`. The collector reads the Mission detail
endpoint, takes the immutable completion Commit SHA from its result evidence, asks GitHub
for pull requests associated with that exact Commit, and requires exactly one PR whose
head SHA matches. It then fetches changed files, Check Runs and commit statuses.

The collector never guesses a PR from a branch name or the latest repository activity.
If the Mission has no immutable completion SHA, or PR association is ambiguous, it stops
with an explicit error. Tokens are read from environment variables and are not serialized.

This still evaluates evidence completeness, not functional correctness. Independent
re-execution in an isolated runner is a separate stage and is not claimed here.
