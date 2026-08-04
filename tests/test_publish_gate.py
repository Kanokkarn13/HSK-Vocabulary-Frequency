from etl.publish_gate import publish_enabled


def test_publish_gate_is_fail_closed_by_default(monkeypatch):
    monkeypatch.delenv("HSK_PUBLISH_ENABLED", raising=False)
    assert not publish_enabled()


def test_publish_gate_accepts_only_explicit_true_values(monkeypatch):
    monkeypatch.setenv("HSK_PUBLISH_ENABLED", "true")
    assert publish_enabled()
    assert publish_enabled("ON")
    assert not publish_enabled("false")
