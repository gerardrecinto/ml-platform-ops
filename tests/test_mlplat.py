import json
import pathlib
import threading
import urllib.error
import urllib.request

import pytest

from mlplat.gate import promote, rollback
from mlplat.model import RegistryError, accuracy, load
from mlplat.service import serve

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOLDOUT = json.loads((ROOT / "tests" / "holdout.json").read_text())
REG = json.loads((ROOT / "registry" / "registry.json").read_text())


def write(tmp_path, reg):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg))
    return p


def test_shipped_models_both_pass_the_holdout():
    assert all(accuracy(m, HOLDOUT) >= 0.9 for m in REG["models"].values())


def test_worse_model_is_refused_and_registry_unchanged(tmp_path):
    reg = json.loads(json.dumps(REG))
    reg["active"] = "v1"
    reg["models"]["bad"] = {"bias": 5.0, "threshold": 0.5, "weights": {"amount_k": 0.0}}
    p = write(tmp_path, reg)
    problems = promote(p, "bad", HOLDOUT)
    assert problems and "below active" in problems[0]
    assert load(p)["active"] == "v1"


def test_equal_or_better_model_is_promoted_and_remembers_previous(tmp_path):
    reg = json.loads(json.dumps(REG))
    reg["active"], reg["previous"] = "v1", None
    p = write(tmp_path, reg)
    assert promote(p, "v2", HOLDOUT) == []
    got = load(p)
    assert got["active"] == "v2" and got["previous"] == "v1"


def test_unknown_and_active_versions_are_refused(tmp_path):
    p = write(tmp_path, REG)
    assert promote(p, "v9", HOLDOUT) == ["v9 is not in the registry"]
    assert promote(p, "v2", HOLDOUT) == ["v2 is already active"]


def test_rollback_swaps_back_and_fails_without_a_previous(tmp_path):
    p = write(tmp_path, REG)
    assert rollback(p) == "v1"
    assert load(p)["active"] == "v1"
    reg = json.loads(json.dumps(REG)); reg["previous"] = None
    with pytest.raises(RegistryError):
        rollback(write(tmp_path, reg))


def test_broken_registry_raises(tmp_path):
    p = tmp_path / "r.json"; p.write_text("{not json")
    with pytest.raises(RegistryError):
        load(p)


@pytest.fixture
def server(tmp_path):
    p = write(tmp_path, REG)
    httpd = serve(p, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd, p
    httpd.shutdown()


def call(httpd, path, body=None):
    url = f"http://127.0.0.1:{httpd.server_address[1]}{path}"
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_score_returns_decision_and_model_version(server):
    httpd, _ = server
    code, body = call(httpd, "/score", {"features": {"amount_k": 2.0, "country_mismatch": 1, "new_device": 1, "velocity_1h": 4}})
    assert code == 200 and json.loads(body)["fraud"] is True and json.loads(body)["model_version"] == "v2"
    code, body = call(httpd, "/score", {"features": {"amount_k": 0.02}})
    assert json.loads(body)["fraud"] is False


def test_bad_body_is_400_and_counted(server):
    httpd, _ = server
    assert call(httpd, "/score", {"nope": 1})[0] == 400
    assert 'mlplat_requests_total{code="400"} 1' in call(httpd, "/metrics")[1]


def test_metrics_have_histogram_and_model_info(server):
    httpd, _ = server
    call(httpd, "/score", {"features": {}})
    text = call(httpd, "/metrics")[1]
    assert 'mlplat_request_duration_seconds_bucket{le="+Inf"} 1' in text
    assert 'mlplat_model_info{version="v2"} 1' in text


def test_bad_reload_keeps_serving_the_old_model_and_flags_it(server):
    httpd, p = server
    p.write_text("{broken")
    assert httpd.state.reload() is False
    assert call(httpd, "/readyz")[0] == 200
    assert call(httpd, "/score", {"features": {}})[1].count('"model_version": "v2"') == 1
    assert "mlplat_reload_failed 1" in call(httpd, "/metrics")[1]
    p.write_text(json.dumps(REG))
    assert httpd.state.reload() is True
    assert "mlplat_reload_failed 0" in call(httpd, "/metrics")[1]


def test_start_with_a_broken_registry_is_not_ready(tmp_path):
    p = tmp_path / "r.json"; p.write_text("nope")
    httpd = serve(p, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert call(httpd, "/readyz")[0] == 503 and call(httpd, "/healthz")[0] == 200
    finally:
        httpd.shutdown()
