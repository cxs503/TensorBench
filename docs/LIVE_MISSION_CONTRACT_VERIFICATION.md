# Live Mission Contract Verification Runbook

The collector is read-only. Use a platform token authorized to read the target Mission and a GitHub token authorized to read the repository and CI evidence.

```bash
export TENSORPLATFORM_API_BASE="https://<platform-host>/<api-prefix>"
export TENSORPLATFORM_TOKEN="<read-only-platform-token>"
export GITHUB_TOKEN="<read-only-github-token>"

python -m tensorbench.cli collect-mission \
  --mission-id <mission-id> \
  --output mission-evaluation.json
```

Inspect these fields in the output:

- `snapshot.acceptance_contract.sha256`
- `snapshot.acceptance_contract.freeze_source`
- `snapshot.acceptance_contract.integrity_status`
- `report.checks[check_id=mission.acceptance_contract]`
- `report.overall_status`

Expected trust interpretation:

- `mission_created` + `verified`: the contract snapshot was declared before execution and its bytes match the fingerprint.
- `legacy_start` + `verified`: snapshot integrity is valid, but pre-execution declaration is not established; the evaluator must remain inconclusive.
- `mismatch` / `invalid`: fail closed.
- Missing or empty criteria: inconclusive, never a pass.

This command also requires an exact Mission completion commit and exactly one associated PR whose head SHA matches it. It does not execute candidate code. Independent isolated re-verification is a separate reviewer-controlled step.

Do not put tokens in command-line arguments, output files, or committed configuration. Environment variables are read by the collector and are not copied into its evidence bundle.
