from app.config import Settings

_DEFAULT_RE = r"^https://[a-z0-9-]+\.trycloudflare\.com$"


def test_regex_none_when_flag_off():
    s = Settings(enable_public_tunnel_cors=False)
    assert s.cors_origin_regex_value is None


def test_regex_default_when_flag_on_and_unset():
    s = Settings(enable_public_tunnel_cors=True, cors_origin_regex="")
    assert s.cors_origin_regex_value == _DEFAULT_RE


def test_regex_explicit_value_when_flag_on():
    s = Settings(enable_public_tunnel_cors=True, cors_origin_regex=r"^https://x$")
    assert s.cors_origin_regex_value == r"^https://x$"


def test_regex_ignored_when_flag_off_even_if_set():
    s = Settings(enable_public_tunnel_cors=False, cors_origin_regex=r"^https://x$")
    assert s.cors_origin_regex_value is None
