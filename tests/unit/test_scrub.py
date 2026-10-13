from faultline.security.scrub import scrub_obj, scrub_text


def test_secret_env_values_and_token_shapes_are_removed():
    env = {"MY_API_TOKEN": "supersecretvalue99", "HARMLESS": "visible-value", "SHORT_SECRET": "abc"}
    text = ("auth supersecretvalue99 and gh" + "p_" + "A" * 30 + " and Bearer " + "abcdefghijklmnop" + "1234 and visible-value "
            "abc stays because values shorter than 6 characters are not treated as secrets")
    out = scrub_text(text, env)
    assert "supersecretvalue99" not in out and "A" * 30 not in out and "abcdefghijklmnop1234" not in out
    assert "visible-value" in out and out.count("[REDACTED]") == 3


def test_scrub_obj_walks_nested_structures():
    env = {"X_PASSWORD": "hunter2hunter2"}
    out = scrub_obj({"a": ["hunter2hunter2", {"b": "ok hunter2hunter2"}], "n": 5}, env)
    assert out == {"a": ["[REDACTED]", {"b": "ok [REDACTED]"}], "n": 5}
