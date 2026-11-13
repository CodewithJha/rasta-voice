"""Same-origin stream checks do not allow arbitrary origins."""

from rasta.origins import origin_allowed
from rasta.settings import clear_settings_cache, get_settings


def test_same_origin_and_cors_list(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    clear_settings_cache()
    settings = get_settings()
    scope = {"scheme": "https", "headers": [(b"host", b"rasta-demo.hf.space")]}
    assert origin_allowed("https://rasta-demo.hf.space", settings, scope)
    assert not origin_allowed("http://rasta-demo.hf.space", settings, scope)
    assert not origin_allowed("https://evil.example", settings, scope)
    assert not origin_allowed("https://rasta-demo.hf.space.evil.example", settings, scope)
    assert not origin_allowed(None, settings, scope)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://preview.example")
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "true")
    clear_settings_cache()
    settings = get_settings()
    proxied = {
        "scheme": "http",
        "headers": [
            (b"host", b"rasta-demo.hf.space"),
            (b"x-forwarded-proto", b"https"),
        ],
    }
    assert origin_allowed("https://rasta-demo.hf.space", settings, proxied)
    assert origin_allowed("https://preview.example", settings, proxied)
    assert not origin_allowed("https://other.hf.space", settings, proxied)
    clear_settings_cache()
