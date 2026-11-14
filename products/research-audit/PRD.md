# ResearchAudit — Product Requirements

**Product ID:** `research-audit` · **Status:** foundation / not implemented · **Initial internal user:** TensorKnowledge.

## Problem and outcome

Research teams receive papers, technical reports and agent-generated research dossiers whose citations, equations, figures and conclusions may not support one another. ResearchAudit produces a traceable audit of claims and supporting evidence; it does not certify that a paper is true or replace peer review.

## Users and workflow

1. Submit PDF/DOCX/Markdown plus optional bibliography, data tables and figure files.
2. Extract text, structure, equations, tables, figures and citation locations while retaining page/region locators.
3. Build claim → evidence → method relationships.
4. Run checks and generate findings with source spans and counter-evidence.
5. Reviewer accepts/rejects/amends findings; export JSON and human-readable report.

## MVP checks

- Citation existence, metadata consistency and duplicate detection.
- Citation-to-claim support: distinguish direct support, partial support, contradiction and no verifiable support; model-assisted and must show quoted source span.
- Internal consistency: claim/table/figure/value mismatch and conflicting statements.
- Equation integrity: symbol/unit consistency, dimensional checks where symbols and units are known; no claim of general proof.
- Method/result/conclusion alignment: sample size, conditions, uncertainty and limitations.
- Unsupported extrapolation and missing counter-evidence prompts.

## Inputs and outputs

Inputs: document files, DOI/URL bibliography, optional source datasets and analysis artifacts. Outputs: structured claims, evidence links, findings, review decisions and audit report. Every extracted span retains document hash, page and character/region offsets.

## Acceptance and blind evaluation

- Curated holdout: at least 100 claim-citation pairs with expert labels across support/partial/contradiction/insufficient evidence.
- Report per-class precision/recall and confusion matrix; do not report only aggregate accuracy.
- Target for pilot: citation metadata precision ≥0.98; support classification macro-F1 ≥0.80 on the labelled holdout; every finding must resolve to a source span or be explicitly marked as a heuristic prompt.
- Human reviewers can reproduce each finding from the cited source.
- Any unresolvable extraction or unavailable source is `inconclusive`, never silently passed.

## Non-goals

Automated paper acceptance, plagiarism verdicts, authorship detection, fabricated peer-review scores, or guaranteed proof of scientific truth.

## First vertical slice

Audit one real TensorKnowledge research report plus its bibliography and available source papers. Start with citation coverage and claim-to-citation traceability before attempting equation reasoning. Record access rights; do not upload paywalled papers unless permitted.
