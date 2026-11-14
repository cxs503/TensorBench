# Independent Isolated Test Runner

The first independent re-execution stage runs an explicitly selected test command
against a clean, exact Git checkout inside an OCI container.

## Requirements

- A dedicated runner host; rootless Podman is preferred.
- A pre-pulled, trusted runner image pinned by immutable `@sha256:<digest>`.
- A clean local Git checkout whose HEAD equals the Mission completion SHA.
- A reviewer-selected command (argv array; no shell string).

The runner refuses mutable image tags, dirty checkouts, revision mismatches, missing
container runtimes, and unsupported engines. It uses no network, a read-only checkout
and root filesystem, dropped Linux capabilities, no-new-privileges, a non-root UID,
and memory/CPU/PID/time limits. It does not pass host environment variables or tokens
into the container.

## Example

```bash
tensorbench reverify-tests \
  --checkout ./worktrees/TensorLBM \
  --revision <full-commit-sha> \
  --image registry.example/tensorbench-runner@sha256:<64-hex-digest> \
  --log-dir ./evidence/mission-123-test-logs \
  -- python -m pytest -q
```

The JSON report includes command, exact revision, image digest reference, exit status,
time bounds, resource limits, stdout/stderr hashes and bounded log excerpts. Full logs are retained in the required `--log-dir`; the report records their paths, byte counts and SHA-256 digests.

## Security and interpretation

This is defense-in-depth, not a formally verified sandbox. Rootless Podman on a
dedicated host is preferred. Docker may rely on a privileged daemon and must only
be used on a trusted isolated runner host. Do not execute untrusted Agent code on
a developer workstation or shared production host. A green test run is evidence
that a command passed in this environment; it is not proof that tests are meaningful,
that the feature works, or that scientific results are correct.

## Attach the result to a criterion

After `reverify-tests` writes its JSON report and retained logs, bind that run to the
specific predeclared acceptance criterion(s). The command verifies both log hashes
before it adds the test record and evidence artifacts:

```bash
tensorbench attach-isolated-run \\
  --bundle mission-123.evidence.json \\
  --report mission-123-test-run.json \\
  --test-id isolated-pytest-rerun \\
  --criterion-id C-IMPLEMENTATION \\
  --output mission-123.evidence.reverified.json
```

The reviewer must explicitly map the run to criterion IDs. A timed-out run becomes
`not_run`; it cannot be counted as a pass. A revision mismatch or altered log is rejected.

## Real container integration

The `Isolated Runner Integration` GitHub Actions workflow builds the minimal test image in `.github/runner/Dockerfile`, captures its local SHA-256 image ID, and executes the evaluator/collector test suites in a real Docker container with the production isolation flags. It then attaches the report and full log fingerprints to a small evidence bundle and uploads the artifacts for review. This validates the actual container path on a GitHub-hosted runner; it does not provision a persistent production runner.
