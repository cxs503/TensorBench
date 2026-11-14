# Physics Dataset Validator — Product Requirements

**Product ID:** `physics-dataset-validator` · **Status:** foundation / not implemented · **Initial users:** TensorData, TensorPhysics, TensorLBM.

## Problem and outcome

Generic tabular data checks cannot establish whether a physical dataset is dimensionally coherent, satisfies declared boundary/initial conditions, obeys expected conservation laws, or aligns across modalities. The product validates data integrity and declared physical constraints before datasets are admitted to training or simulation workflows.

## MVP workflow

1. Resolve TensorData dataset ID/version and immutable manifest; do not copy its catalog or rights registry.
2. Inspect schema, units, coordinate/time axes, missingness, ranges and mesh/field metadata.
3. Load a versioned domain validation profile (physics, variables, units, assumptions, tolerances).
4. Run deterministic checks and optional statistical/model-assisted anomaly checks.
5. Produce findings, metric summaries and a TensorData quality-report reference.
6. Block promotion when required checks fail or rights are not cleared.

## MVP checks

- Shape, dtype, null/NaN/Inf, coordinate monotonicity and timestamp consistency.
- Unit and dimensional consistency; unknown units are unresolved, not assumed SI.
- Boundary and initial condition completeness and declared-condition compliance.
- Conservation residuals (mass, momentum, energy) only where required variables and control-volume definitions exist.
- Physical bounds and constitutive constraints declared by the profile.
- Multimodal alignment: timestamps, coordinate frames, mesh mapping and sensor/simulation correspondence.
- Train/validation/test leakage by entity, trajectory, time window and near-duplicate fingerprints.
- Provenance, rights, transformation lineage and dataset-version reproducibility.

## Initial pilot: ship-flow data

Start with a small, real TensorLBM/TensorPhysics ship-flow dataset and an explicit profile. Include known-good samples plus deliberately corrupted fixtures: unit scale error, shuffled time, missing boundary metadata, broken conservation, coordinate mismatch and split leakage. Synthetic corruptions must be labelled and kept separate from real evidence.

## Acceptance and blind evaluation

- At least 50 labelled dataset cases/perturbations across the above defect classes.
- 100% detection of deterministic injected errors in the pilot fixture suite.
- No false pass for unknown units, missing required boundary metadata or unresolved rights.
- Report false-positive rate on known-good data; target ≤5% before pilot release.
- Every physical check records formula, variables, units, discretization/control volume, tolerance and applicability assumptions.

## Non-goals

A universal physics oracle, automatic proof of simulation correctness, solver replacement, or automatic approval of data for model training. TensorData remains authoritative for asset lifecycle and rights; this product supplies quality evidence.
