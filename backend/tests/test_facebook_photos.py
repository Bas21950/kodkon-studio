from pathlib import Path
from types import SimpleNamespace

from app.services import facebook


def test_publish_photos_uploads_all_images_then_publishes_ordered_album(tmp_path: Path, monkeypatch):
    calls = []

    def fake_request(method, url, token, **kwargs):
        calls.append((method, url, token, kwargs))
        if url.endswith("/photos"):
            return {"id": f"photo-{len(calls)}"}
        return {"id": "page-post-123"}

    monkeypatch.setattr(facebook, "_request", fake_request)
    image_paths = [tmp_path / "first.jpg", tmp_path / "second.png", tmp_path / "third.jpg"]
    for path in image_paths:
        path.write_bytes(b"image")

    post_id = facebook.publish_photos("page-1", "token", image_paths, "caption")

    assert post_id == "page-post-123"
    assert len(calls) == 4
    assert all(call[1].endswith("/page-1/photos") for call in calls[:3])
    assert all(call[3]["data"] == {"published": "false", "temporary": "true"} for call in calls[:3])
    feed_call = calls[-1]
    assert feed_call[1].endswith("/page-1/feed")
    assert feed_call[3]["data"] == {
        "message": "caption",
        "attached_media[0]": '{"media_fbid": "photo-1"}',
        "attached_media[1]": '{"media_fbid": "photo-2"}',
        "attached_media[2]": '{"media_fbid": "photo-3"}',
    }


def test_photo_set_preflight_checks_count_size_and_aggregate():
    valid = SimpleNamespace(original_name="photo.jpg", byte_size=10, width=None)
    assert facebook.photo_set_preflight([valid, valid]) is None
    assert facebook.photo_set_preflight([valid] * 7) is not None
    oversized = SimpleNamespace(original_name="photo.jpg", byte_size=20 * 1024 * 1024)
    assert facebook.photo_set_preflight([oversized, oversized]) is not None


def test_get_post_insights_reads_metrics_and_engagement_counts(monkeypatch):
    calls = []

    def fake_request(method, url, token, **kwargs):
        calls.append((url, kwargs.get("params", {})))
        params = kwargs.get("params", {})
        if url.endswith("/insights"):
            metric = params["metric"]
            return {"data": [{"values": [{"value": {"post_media_view": 120, "post_total_media_view_unique": 95,
                                                        "post_clicks": 7}[metric]}]}]}
        return {
            "reactions": {"summary": {"total_count": 12}},
            "comments": {"summary": {"total_count": 3}},
            "shares": {"count": 2},
        }

    monkeypatch.setattr(facebook, "_request", fake_request)

    metrics = facebook.get_post_insights("page_123", "secret")

    assert metrics == {
        "views": 120,
        "viewers": 95,
        "clicks": 7,
        "reactions": 12,
        "comments": 3,
        "shares": 2,
        "metric_errors": [],
    }
    assert len(calls) == 4
