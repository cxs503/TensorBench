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
  -- python -m pytest -q
```

The JSON report includes command, exact revision, image digest reference, exit status,
time bounds, resource limits, stdout/stderr hashes and bounded log excerpts.

## Security and interpretation

This is defense-in-depth, not a formally verified sandbox. Rootless Podman on a
dedicated host is preferred. Docker may rely on a privileged daemon and must only
be used on a trusted isolated runner host. Do not execute untrusted Agent code on
a developer workstation or shared production host. A green test run is evidence
that a command passed in this environment; it is not proof that tests are meaningful,
that the feature works, or that scientific results are correct.
