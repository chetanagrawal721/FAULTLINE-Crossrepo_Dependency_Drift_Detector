"""HR-2: a witness re-runs live (3 fresh executions per world) and still reproduces."""
import pytest

from faultline.witnesses.rerun import rerun_witness
from tests.integration.test_live import d_scenario  # noqa: F401

pytestmark = pytest.mark.docker


def test_a_witness_reruns_live_with_six_fresh_executions_and_reproduces(d_scenario, daemon, image):  # noqa: F811
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    conn, res, ids = d_scenario
    wid = conn.execute("SELECT id FROM witness ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    before = conn.execute("SELECT COUNT(*) FROM oracle_run WHERE provenance='FRESH_EXECUTION'").fetchone()[0]
    r = rerun_witness(conn, SandboxClient(port=daemon.port, token=TOKEN, timeout=600), image, wid)
    assert r.reproduced and (r.reference_passes, r.consumer_failures, r.fresh_runs) == (3, 3, 6) and r.seconds > 0
    assert conn.execute("SELECT COUNT(*) FROM oracle_run WHERE provenance='FRESH_EXECUTION'").fetchone()[0] == before + 6      # six NEW fresh records
    assert conn.execute("SELECT COUNT(*) FROM witness").fetchone()[0] == 1                                                    # no second witness for the same key
