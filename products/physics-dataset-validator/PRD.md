# Physics Dataset Validator — Product Requirements

**Product ID:** `physics-dataset-validator` · **Status:** partially implemented; real-world workflow not yet verified · **Initial users:** TensorData, TensorPhysics, TensorLBM.

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


## Implementation status (verified against repository source, 2026-11-14)

**Overall: partially implemented; no TensorLBM ship-flow end-to-end pilot completed.**

Implemented in the current codebase:
- CSV schema/required-variable, numeric finiteness, axis monotonicity and basic metadata checks.
- Unit metadata validation and supported conversions.
- Declared physical-range checks with conservative unresolved outcomes when assumptions are insufficient.
- Entity-level split-leakage checks, rights gating and report fingerprinting.
- Focused validator tests (the preceding implementation run reported 79 passed, 1 skipped).

Not yet implemented or not yet demonstrated:
- Executable conservation-law checks with explicit control-volume/discretization definitions.
- Initial/boundary-condition compliance checks.
- Multimodal time/coordinate-frame/mesh alignment.
- NetCDF/HDF5/VTK and other field/mesh-native formats.
- Validation against a real TensorLBM ship-flow dataset and labelled good/bad samples.

Release interpretation:
- Unsupported conservation, boundary or initial-condition checks must return `inconclusive`, never pass.
- CSV fixture success is not evidence of physical correctness for a solver dataset.
- A physics profile must declare variables, units, formula, discretization, tolerance and applicability assumptions before a physical check can run.
