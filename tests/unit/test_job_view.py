"""NFR-6: every job reports a status, a duration and a failure class."""
import time

from faultline.storage import jobs


def claim(conn, key):
    j, _ = jobs.create_job(conn, "noop", {}, key)
    return j, jobs.claim_next(conn, "w1", 30)


def test_a_finished_job_reports_duration_and_wait_and_no_failure(conn):
    j, c = claim(conn, "a")
    time.sleep(0.05)
    jobs.complete(conn, j.job_id, "w1", {"ok": True})
    v = jobs.get_job(conn, j.job_id)
    assert v.status.value == "DONE" and v.duration_ms >= 50 and v.queue_wait_ms >= 0 and v.failure_class is None and v.retried_after is None


def test_a_failed_job_reports_its_failure_class(conn):
    j, c = claim(conn, "b")
    jobs.fail(conn, j.job_id, "w1", {"code": "HANDLER_ERROR", "message": "boom"}, retryable=False)
    v = jobs.get_job(conn, j.job_id)
    assert v.status.value == "FAILED" and v.failure_class == "HANDLER_ERROR" and v.duration_ms is not None


def test_a_cancelled_job_reports_cancelled(conn):
    j, c = claim(conn, "c")
    jobs.request_cancel(conn, j.job_id)
    jobs.mark_cancelled(conn, j.job_id, "w1")
    assert jobs.get_job(conn, j.job_id).failure_class == "CANCELLED"


def test_a_job_that_needed_a_second_attempt_says_how_the_first_ended(conn):
    j, c = claim(conn, "d")
    jobs.fail(conn, j.job_id, "w1", {"code": "TRANSIENT", "message": "blip"}, retryable=True)
    again = jobs.claim_next(conn, "w2", 30)
    while again is None:                                                       # a retried job waits out its backoff
        time.sleep(0.2)
        again = jobs.claim_next(conn, "w2", 30)
    jobs.complete(conn, j.job_id, "w2", {})
    v = jobs.get_job(conn, j.job_id)
    assert v.status.value == "DONE" and v.attempts == 2 and v.retried_after == "RETRY" and v.failure_class is None


def test_a_job_still_running_reports_time_so_far(conn):
    j, c = claim(conn, "e")
    time.sleep(0.05)
    v = jobs.get_job(conn, j.job_id)
    assert v.status.value == "RUNNING" and v.duration_ms >= 50
