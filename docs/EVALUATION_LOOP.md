# Benchmark → Platform Evaluation Loop

TensorBench is only useful as an evaluation layer if its verdicts actually reach
the records that decide credit and evidence grades. This document is the contract
for that path, and an honest account of what is proven and what is not.

## 1. The chain

```text
benchmark specification (criteria declared BEFORE execution)
   └─ runner           → <run_id>.result.json  (metrics, samples, acceptance, score, provenance hashes)
        ├─ compare     → <run_id>.comparison.json (comparability checks, real deltas, verdict, category hint)
        └─ publish     → evaluation payload  → POST /tensor/outcome-evaluations   (outcome_evaluations)
                       → capability delta   → booked through the mission acceptance hook
                                             (tensor_capability_deltas)
```

Three consumers of one record:

1. **S-grade evidence.** A benchmark whose predeclared criteria *passed* is an
   admissible evidence source for `S3`, but only together with a declared,
   comparable baseline; without a baseline the same evidence is registered `S2`
   (the platform requires a baseline for S2/S3 and caps evidence to `E1` when the
   five-element chain is incomplete). A failed benchmark goes to the negative
   track `S-N` — it is never silently upgraded.
2. **Capability delta.** `compare.py` produces the only numbers that belong in a
   delta: the primary-metric ratio, the score change (criteria pass ratio) and the
   criteria pass/fail transition. "unchanged" is a first-class verdict and maps to
   `no_substantive_delta`; a performance win in a run that failed its correctness
   gate is reported as `regressed`, never as an improvement.
3. **Credit.** The delta carries `evidence.credit_hint` with its numbers
   (`baseline`, `candidate`, `improvement_ratio`, `score_delta`) and the delta
   category, so the credit ledger can consume benchmark movement instead of prose.
   Credit is *booked* by the platform's acceptance hook, not by TensorBench.

## 2. Commands

```bash
# one benchmark, repeated with a warm-up that is executed but not measured
python -m tensorbench run --spec benchmarks/reference/stencil2d5pt/naive.benchmark.json --output runs/stencil2d5pt

# compare a candidate against a basline (thresholds predeclared in the spec)
python -m tensorbench compare --baseline runs/.../naive.result.json --candidate runs/.../row.result.json

# build the platform payloads (dry run), then POST them
python -m tensorbench publish --result runs/.../row.result.json --baseline runs/.../naive.result.json \
    --mission-id <id> --contributor <agent> --reviewer <auditor> --output runs/stencil2d5pt
python -m tensorbench publish ... --post        # add --post to write outcome_evaluations
```

`publish` writes `<run_id>.comparison.json` and `<run_id>.publish.json` next to the
run record; both keep the artifact `sha256` values that end up in the evidence
references, so a reviewer can re-hash them independently.

## 3. Evidence-chain element shapes (learned the hard way)

The platform validates each element, not just its presence: `theory` needs a
URL/DOI/`derivation:` anchor, `code` a commit sha (or `repo@sha`), `config`
`sha256:<64 hex>`, `data` a path or `file:`/`run:` anchor, and `report` a positive
platform report id. A first live write failed all five because they were free
text; the chain was judged *invalid*, the evidence level was capped to `E1` and the
`S3` claim was demoted to `candidate`. The builder now emits the required shapes
and a test pins the behaviour. **Lesson:** an evaluation row can exist and still be
worthless — check the `reason_codes`, not just the HTTP status.

## 4. What the first end-to-end run proved

Reference workload `tensorbench.reference.stencil2d5pt` (2-D five-point heat
stencil, analytic reference `u = A exp(-2 α k² t) sin(kx) sin(ky)`), two
implementations of the same scheme, 7 measured repetitions each after one discarded
warm-up, identical declared configuration (so the configuration hash matches):

| quantity | naive | row-slice | note |
|---|---|---|---|
| `max_rel_error` vs analytic | 1.737e-05 | 1.737e-05 | criterion ≤ 3.0e-3 — PASS (both) |
| `l2_rel_error` | 2.446e-05 | 2.446e-05 | criterion ≤ 3.0e-3 — PASS (both) |
| `conservation_drift` | 0.0 | 0.0 | criterion ≤ 1e-9 — PASS (both) |
| `throughput_mlups` (median of 7) | 1.083 | 1.827 | ratio 1.6865 ≥ predeclared 1.10 |
| score (criteria pass ratio) | 1.0 | 1.0 | no correctness was traded for speed |

Verdict: `improved` → `capability_extension`. The two implementations agree
bit-for-bit on the final field (`field_sum` identical), so the speed difference is
not a numerical difference.

## 5. Limits (do not over-read this)

* One size (n=96), one machine (loongarch64, shared host), pure-Python kernels:
  the ratio is a property of *this* workload, not of stencils in general.
* Repetition samples still scatter (per-sweep loop timings vary with host load);
  medians are reported with the full sample list, and the verdict threshold was
  declared before the runs.
* The criteria bound the *declared* tolerances only. Passing them is not a claim
  that the numerical method is validated, and TensorBench does not redefine any
  solver's acceptance criteria.
* Comparability is enforced mechanically (benchmark version, workload version,
  configuration hash, criteria hash, precision) but hardware differences are only
  disclosed, not controlled.
* Evaluation rows are only accepted for `succeeded` missions, so the first proof
  used a purpose-built, immediately-approved proof mission (`repo=TensorBench`)
  whose goal states exactly that; the mission and the evaluation are linked by id.
