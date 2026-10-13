"""SR-4: the egress proxy's allow/deny decisions, without a network."""
import pytest

from faultline.oracles.harness.egress_proxy import ALLOWED_HOSTS, decide, is_public

PUBLIC = lambda host: ["140.82.112.3"]  # noqa: E731


def test_allowlisted_hosts_on_443_are_allowed_and_connect_to_the_checked_address():
    for host in ALLOWED_HOSTS:
        allowed, reason, addresses = decide(host, 443, PUBLIC)
        assert allowed and addresses == ["140.82.112.3"], (host, reason)
    assert decide("GitHub.com.", 443, PUBLIC)[0]                       # case and the trailing dot do not matter


@pytest.mark.parametrize("host,port", [
    ("example.com", 443), ("evil.github.com", 443), ("github.com.evil.io", 443), ("pypi.org.attacker.net", 443),
    ("github.com", 80), ("github.com", 22), ("github.com", 8443), ("pypi.org", 0),
])
def test_other_names_and_ports_are_refused(host, port):
    assert decide(host, port, PUBLIC)[0] is False


@pytest.mark.parametrize("literal", ["169.254.169.254", "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "0.0.0.0", "8.8.8.8", "::1", "fd00::1", "140.82.112.3"])
def test_ip_literals_are_always_refused(literal):
    assert decide(literal, 443, PUBLIC) == (False, "IP literals are not allowed", [])


@pytest.mark.parametrize("answer", ["169.254.169.254", "127.0.0.1", "10.1.2.3", "192.168.0.9", "172.20.0.2", "100.64.0.1", "::1", "fe80::1", "fc00::1", "::ffff:10.0.0.1"])
def test_an_allowlisted_name_that_resolves_to_a_non_public_address_is_refused(answer):
    allowed, reason, addresses = decide("github.com", 443, lambda h: [answer])
    assert allowed is False and addresses == [] and "non-public" in reason


def test_one_bad_answer_among_good_ones_refuses_the_name():
    assert decide("pypi.org", 443, lambda h: ["151.101.0.223", "10.0.0.5"])[0] is False


def test_resolution_failure_is_a_refusal_not_an_error():
    def boom(host):
        raise OSError("no dns")
    assert decide("pypi.org", 443, boom)[0] is False
    assert decide("pypi.org", 443, lambda h: [])[0] is False


def test_public_address_classifier():
    assert is_public("140.82.112.3") and is_public("2606:4700::1111")
    assert not any(is_public(a) for a in ["169.254.169.254", "127.0.0.1", "10.0.0.1", "224.0.0.1", "not-an-ip"])


def test_every_resolved_address_is_returned_so_the_proxy_can_fall_back_and_all_must_be_public():
    allowed, _, addresses = decide("pypi.org", 443, lambda h: ["151.101.0.223", "151.101.64.223", "2a04:4e42::223"])
    assert allowed and addresses == ["151.101.0.223", "151.101.64.223", "2a04:4e42::223"]
