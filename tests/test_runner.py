import json
import sys

from tensorbench.runner import run_benchmark


def make_spec(command, timeout=5):
    return {
        "benchmark": {"benchmark_id": "test.smoke", "version": "1.0.0"},
        "workload": {
            "workload_id": "smoke",
            "version": "1.0.0",
            "command": command,
        },
        "execution": {"timeout_seconds": timeout},
    }


def test_success_writes_result_and_logs(tmp_path):
    result = run_benchmark(
        make_spec([sys.executable, "-c", "print('hello tensorbench')"]),
        tmp_path,
    )

    assert result["execution"]["status"] == "success"
    assert result["execution"]["exit_code"] == 0
    assert result["metrics"][0]["name"] == "wall_time"
    assert len(result["artifacts"]) == 2

    result_files = list(tmp_path.glob("*.result.json"))
    assert len(result_files) == 1
    persisted = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert persisted["run_id"] == result["run_id"]


def test_nonzero_exit_is_recorded_as_failure(tmp_path):
    result = run_benchmark(
        make_spec([sys.executable, "-c", "raise SystemExit(7)"]),
        tmp_path,
    )

    assert result["execution"]["status"] == "failed"
    assert result["execution"]["exit_code"] == 7
    assert result["validation"]["execution"] == "failed"


def test_timeout_is_recorded(tmp_path):
    result = run_benchmark(
        make_spec([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1),
        tmp_path,
    )

    assert result["execution"]["status"] == "timeout"
    assert result["execution"]["exit_code"] is None


def test_invalid_shell_string_command_is_rejected(tmp_path):
    spec = make_spec("echo unsafe")
    try:
        run_benchmark(spec, tmp_path)
    except ValueError as exc:
        assert "string array" in str(exc)
    else:
        raise AssertionError("string command must be rejected")
