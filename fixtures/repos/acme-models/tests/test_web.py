import importlib.util

import pytest

# The web extra is optional. A world WITHOUT Flask skips these tests; a world where Flask is present but broken must
# run them and fail (importorskip would hide that by skipping on ImportError).
pytestmark = pytest.mark.skipif(importlib.util.find_spec("flask") is None, reason="web extra not installed")


def test_show_customer():
    from acme_models.web import make_app

    client = make_app().test_client()
    body = client.get("/customers/3").get_json()
    assert body["customer_id"] == 3 and body["loyalty_points"] == 0
