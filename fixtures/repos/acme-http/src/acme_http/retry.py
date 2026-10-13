"""Retry policies. Importing this module works with every urllib3; one of the calls below does not."""
from urllib3.util.retry import Retry


def make_retry():
    """Retry GET three times. method_whitelist was renamed allowed_methods in urllib3 1.26 and removed in urllib3 2.0."""
    return Retry(total=3, method_whitelist=["GET"])


def make_quick_retry():
    """Uses only keywords that exist in every urllib3 version: it must never be reported."""
    return Retry(total=2, backoff_factor=0.1)
