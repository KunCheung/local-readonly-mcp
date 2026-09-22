from server import _is_loopback_host


def test_loopback_hosts() -> None:
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert _is_loopback_host("localhost")


def test_non_loopback_hosts() -> None:
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("192.168.1.10")
