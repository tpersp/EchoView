from echoview import embed_utils


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_youtube_oembed_lookup_uses_cache(monkeypatch):
    calls = []
    url = "https://www.youtube.com/watch?v=abc123def45"

    def fake_get(endpoint, params=None, timeout=0):
        calls.append((endpoint, params["url"], timeout))
        return _FakeResponse({"title": "Cached Title"})

    embed_utils.reset_oembed_cache()
    monkeypatch.setattr(embed_utils.requests, "get", fake_get)

    first = embed_utils.youtube_oembed_lookup(url)
    second = embed_utils.youtube_oembed_lookup(url)

    assert first == {"title": "Cached Title"}
    assert second == first
    assert calls == [(embed_utils.OEMBED_ENDPOINT, url, 6)]
