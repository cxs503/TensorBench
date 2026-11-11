"""Guards for the m14899 / KPI-BENCH-10 audit (docs/audit_m14899/).

The audit verdict rests on arithmetic that must stay checkable: the audited
implementation is exactly ITTC-1957 friction + ITTC-1978 summation, and its
three cases score 1/3 against the platform 15% standard while all three are
marked "passed" by one-sided thresholds widened to 27% / 32%.

These tests re-derive those numbers from the case parameters transcribed out of
the audited (git-untracked) spec files, so a future change to the audit numbers
cannot drift away from the evidence without turning a test red.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "audit_m14899" / "verify_bench10.py"
_spec = importlib.util.spec_from_file_location("verify_bench10", _SCRIPT)
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)

ROWS = {name: verify.replicate(case) for name, case in verify.CASES.items()}


def test_implementation_is_exactly_ittc78():
    """Audited workload arithmetic == independent ITTC-78 replication."""
    for name, row in ROWS.items():
        assert row["replication_delta_Ct"] == pytest.approx(0.0, abs=1e-15), name
        assert row["replication_delta_Fn"] == pytest.approx(0.0, abs=1e-15), name


def test_reported_errors():
    """Relative errors against the external anchors, as published in report #13981."""
    assert ROWS["suboff"]["err_vs_anchor_pct"] == pytest.approx(25.82, abs=0.05)
    assert ROWS["dtmb5415"]["err_vs_anchor_pct"] == pytest.approx(24.73, abs=0.05)
    assert ROWS["kvlcc2"]["err_vs_anchor_pct"] == pytest.approx(10.77, abs=0.05)


def test_only_one_case_meets_platform_15pct_standard():
    passing = [name for name, row in ROWS.items() if row["passes_platform_15pct"]]
    assert passing == ["kvlcc2"]


def test_all_cases_pass_only_because_tolerances_were_widened():
    """Two tolerances exceed the platform standard; without them 2/3 cases fail."""
    widened = [n for n, r in ROWS.items() if r["case"]["spec_tolerance_pct"] > verify.PLATFORM_ERROR_LIMIT_PCT]
    assert sorted(widened) == ["dtmb5415", "suboff"]
    assert sum(r["passes_spec_threshold_rule"] for r in ROWS.values()) == 3


def test_suboff_anchor_unreachable_with_physical_form_factor():
    """Even (1+k)=1, Cw=0 leaves SUBOFF +20.4% off the anchor -> anchor/model mismatch."""
    row = ROWS["suboff"]
    assert row["err_floor_pct"] == pytest.approx(20.43, abs=0.05)
    assert row["err_floor_pct"] > verify.PLATFORM_ERROR_LIMIT_PCT
    assert row["form_factor_physical"] is False


def test_dtmb5415_is_run_off_its_anchor_froude_number():
    """Case speed gives Fn=0.2932 while the anchor is quoted at Fr=0.280 (+4.7%)."""
    row = ROWS["dtmb5415"]
    assert row["Fn"] == pytest.approx(0.29321, abs=1e-4)
    assert row["Fn_vs_anchor_delta_pct"] > 4.0


def test_kpi_coverage_is_below_target():
    assert len(verify.CASES) == 3
    assert len(verify.CASES) < verify.KPI_CASE_TARGET