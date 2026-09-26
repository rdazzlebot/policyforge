"""The suite may not reach past this machine (#432).

`conftest.no_network` refuses DNS and connections beyond loopback. These
pin what it refuses AND what it must allow: a guard specified only by what
it refuses is satisfied by refusing everything.
"""

from __future__ import annotations

import socket

import pytest
from conftest import NetworkUsedInTest


@pytest.mark.parametrize("host", ["www.ecfr.gov", "169.254.169.254", "8.8.8.8", "example.com"])
def test_a_lookup_past_this_machine_is_refused_naming_the_host(host):
    with pytest.raises(NetworkUsedInTest, match=host.replace(".", r"\.")):
        socket.getaddrinfo(host, 443)


def test_a_connection_past_this_machine_is_refused_before_it_is_made():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkUsedInTest):
            sock.connect(("93.184.216.34", 80))
        with pytest.raises(NetworkUsedInTest):
            sock.connect_ex(("93.184.216.34", 80))
    finally:
        sock.close()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_loopback_is_allowed(host):
    """Tests name `localhost:11434` with the transport stubbed. If a stub
    misses, the test should fail on its own terms, not on this guard."""
    try:
        socket.getaddrinfo(host, 80)
    except NetworkUsedInTest:  # pragma: no cover - the failure being guarded
        pytest.fail(f"loopback {host!r} was refused")
    except OSError:
        pass  # e.g. no IPv6 on this machine: a real answer, not the guard


def test_the_refusal_is_not_an_oserror():
    """An HTTP client reads an OSError as a connection failure to retry or to
    report as the server's; this has to surface as what it is."""
    assert not issubclass(NetworkUsedInTest, OSError)


def test_boto3_is_told_not_to_ask_the_instance_metadata_service():
    import os

    assert os.environ.get("AWS_EC2_METADATA_DISABLED") == "true"
