# Benchmark Specification Contract

This document defines the minimum information required to make a benchmark understandable, executable, and auditable.

## 1. Required identity

Every benchmark must declare:

- `benchmark_id`: stable, machine-readable identifier;
- `name`: human-readable name;
- `domain`: scientific, data, AI, agent, application, or another declared category;
- `version`: immutable specification version;
- `owner`: responsible project or maintainer;
- `description`: what is being evaluated and why;
- `status`: proposed, experimental, validated, deprecated.

## 2. Workload definition

Specify:

- workload identifier and version;
- input dataset references and checksums where applicable;
- input-generation procedure if generated;
- configuration and parameter values;
- expected output type and location;
- scale parameters (for example grid size, particle count, sequence length, or batch size);
- warm-up and measured iteration policy.

A benchmark must not rely on undocumented local files or hidden manual steps.

## 3. Metrics

Each metric must define:

- name and meaning;
- unit;
- whether it is directly measured or derived;
- aggregation method (single value, mean, median, percentile, minimum, maximum, etc.);
- measurement tool or calculation formula;
- whether lower or higher is better, if meaningful.

Typical metric families include:

| Family | Examples |
|---|---|
| Correctness | pass/fail, residual, relative error, conservation error |
| Performance | wall time, throughput, latency, speedup |
| Resource | peak memory, GPU memory, CPU/GPU utilization |
| Scaling | strong/weak scaling efficiency, parallel efficiency |
| Robustness | failure rate, timeout rate, sensitivity |
| AI/data quality | task accuracy, retrieval quality, schema validity, data completeness |
| Agent productivity | accepted artifact rate, verified task completion, cost per accepted result |

Metrics must not be compared if their definitions differ.

## 4. Acceptance criteria

Correctness criteria are mandatory for benchmarks where correctness can be evaluated. State reference source, tolerance, and comparison method.

Scientific benchmarks should declare applicable invariants and domain constraints, such as conservation, convergence, stability, or comparison to analytical/experimental references.

Performance-only benchmarks must say so explicitly and must not imply scientific validation.

## 5. Environment

Record relevant details, including:

- CPU model and core count;
- GPU model, count, and memory, if used;
- RAM;
- operating system and kernel;
- compiler/interpreter/runtime versions;
- key library and driver versions;
- precision mode;
- thread/process count;
- distributed topology when applicable.

Unknown fields should be omitted or marked unknown, never guessed.

## 6. Run protocol

Declare setup, warm-up, measured repetitions, timeout, resource limits, and cleanup behavior. Keep setup time separate from measured execution time when appropriate.

Failed, timed-out, interrupted, and invalid runs must remain visible in the evidence history.

## 7. Result and validation

A run result must link to the exact benchmark version, implementation revision, workload, configuration, environment, measurements, and artifacts.

Validation states must be explicit and layered. "Executed successfully" does not mean "scientifically validated"; "schema-valid" does not mean "reproducible".

## 8. Comparability

A comparison report must state whether runs share compatible:

- benchmark specification and version;
- workload and input data;
- correctness criteria;
- precision and algorithm settings;
- hardware and runtime conditions.

Any mismatch must be disclosed. Do not produce an unqualified leaderboard from incompatible runs.

## 9. Contribution checklist

- [ ] Benchmark purpose and owner are clear.
- [ ] Specification is versioned.
- [ ] Inputs and provenance are recorded.
- [ ] Metrics have units and definitions.
- [ ] Correctness criteria and tolerances are declared, or the benchmark is explicitly performance-only.
- [ ] Environment and run protocol are recorded.
- [ ] Outputs and artifacts are traceable.
- [ ] License and redistribution terms are documented.
- [ ] A rerun procedure is provided.
