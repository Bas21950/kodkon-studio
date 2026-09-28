import pytest
import uuid
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.services.ai_jobs import image_post_copy_prompt, product_copy_prompt, product_info_for_ai
from app.main import append_affiliate_link
from app.schemas import validate_http_url
from app import main as main_module

ORIGIN = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def product_client():
    with TestClient(main_module.app) as client:
        yield client


def test_affiliate_link_is_added_to_post_and_comment_and_not_duplicated():
    url = "https://s.shopee.co.th/example"
    post = append_affiliate_link("แคปชั่นสินค้า", url)
    comment = append_affiliate_link("สนใจดูรายละเอียดได้เลย", url, default_label="🛒 ดูสินค้า")
    assert post.endswith(f"พิกัดสินค้า: {url}")
    assert comment.endswith(f"🛒 ดูสินค้า: {url}")
    assert append_affiliate_link(post, url) == post
    assert append_affiliate_link(comment, url, default_label="🛒 ดูสินค้า") == comment


def test_legacy_product_fields_are_combined_into_one_ai_reference():
    project = SimpleNamespace(
        product_name="ชั้นวางรองเท้า",
        product_details="โครงเหล็ก วางรองเท้าได้หลายคู่",
        product_source_details="ประกอบง่าย",
        review_evidence="รีวิวบอกว่าประหยัดพื้นที่",
        product_review_summary=None,
        product_average_rating=4.8,
        product_review_count=1234,
        discount_text="ลด 20%",
    )
    info = product_info_for_ai(project)
    assert "ชื่อสินค้า:\nชั้นวางรองเท้า" in info
    assert "รีวิวหรือความคิดเห็นที่ผู้ใช้ให้:\nรีวิวบอกว่าประหยัดพื้นที่" in info
    assert "4.8/5 จาก 1,234 รีวิว" in info
    assert "ลด 20%" in info
    assert "source_url" not in info


def test_caption_prompt_requires_natural_copy_grounded_in_the_single_info_field():
    product_info = "เสื้อคอตตอน สีดำ/ขาว ไซซ์ S–XL รอบอก 96–112 ซม. รีวิว 4.8/5"
    prompt = product_copy_prompt({"product_info": product_info}, "caption")
    assert product_info in prompt
    assert "ยึดประเภทสินค้าและข้อเท็จจริงตามนั้น" in prompt
    assert "ไม่ต้องกวน ไม่เล่นมุก ไม่เร่งหรือสั่งให้ซื้อ" in prompt
    assert "ชื่อสินค้า วิธีใช้หรือประโยชน์" in prompt
    assert "ยาวพอดีกับข้อมูล" in prompt
    assert "วัสดุ ขนาด วิธีใช้" in prompt
    assert "ห้ามใส่ URL ใน caption" in prompt


def test_image_caption_prompt_uses_natural_thai_and_covers_key_facts():
    product_info = "เสื้อยืดผ้าคอตตอน ไซซ์ S–XL มีดำและขาว ลด 20% โอนก่อนเท่านั้น ส่งช้า"
    prompt = image_post_copy_prompt(product_info)
    assert product_info in prompt
    assert "ไม่ต้องกวน ไม่เล่นมุก ไม่ฮาร์ดเซล" in prompt
    assert "ชื่อหรือประเภทสินค้า ใช้ทำอะไร" in prompt
    assert "เหมาะกับใครหรือสถานการณ์ไหน" in prompt
    assert "Affiliate link จริงต่อท้าย" in prompt
    assert "กวน แสบ มั่นใจ แหวกแนว" not in prompt
    assert "เรียบเรียงใจความใหม่ให้อ่านลื่น" in prompt
    assert "เลือกเฉพาะรายละเอียดที่ช่วยให้เข้าใจหรือตัดสินใจได้" in prompt
    assert "ไม่ต้องแจกแจงสเปกทุกข้อหรือทำรายการยาว" in prompt
    assert "ห้ามแต่งชื่อยี่ห้อ/รุ่น สเปก ราคา โปร คะแนน รีวิว" in prompt


def test_product_links_must_be_public_http_urls():
    assert validate_http_url(" https://s.shopee.co.th/example ") == "https://s.shopee.co.th/example"
    for url in ("file:///C:/private", "http://localhost/product", "http://127.0.0.1/product", "https://user:pass@example.com/item"):
        try:
            validate_http_url(url)
        except ValueError:
            continue
        raise AssertionError(f"unsafe URL was accepted: {url}")


def test_saving_single_product_info_clears_legacy_page_snapshot(product_client):
    project = product_client.post(
        "/api/projects", headers=ORIGIN,
        json={"title": "ข้อมูลสินค้า", "source_url": "https://shopee.co.th/product/example"},
    ).json()
    with main_module.SessionLocal.begin() as db:
        saved = db.get(main_module.Project, project["id"])
        saved.product_source_details = "รายละเอียดเก่าจากหน้าร้าน"
        saved.product_average_rating = 4.8
        saved.product_review_count = 120
        saved.product_review_summary = "รีวิวเก่า"

    response = product_client.patch(
        f"/api/projects/{project['id']}", headers=ORIGIN,
        json={"product_name": "", "product_details": "รายละเอียดรวมและรีวิว", "review_evidence": "", "discount_text": "", "source_url": ""},
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["product_details"] == "รายละเอียดรวมและรีวิว"
    assert saved["product_source_details"] is None
    assert saved["product_average_rating"] is None
    assert saved["product_review_count"] is None
    assert saved["product_review_summary"] is None


def test_image_post_keeps_multiple_images_product_info_and_affiliate_links(product_client):
    image = b"\x89PNG\r\n\x1a\npayload"
    second_image = b"\xff\xd8\xffpayload"
    affiliate_url = "https://s.shopee.co.th/example"
    response = product_client.post(
        "/api/image-posts",
        headers=ORIGIN,
        files=[
            ("image_files", ("post-image.png", image, "image/png")),
            ("image_files", ("post-image-2.jpg", second_image, "image/jpeg")),
        ],
        data={
            "caption": "แคปชั่นสินค้า",
            "comment_text": "ดูรายละเอียดเพิ่มเติมได้ที่นี่",
            "affiliate_url": affiliate_url,
            "product_details": "รายละเอียดและรีวิวที่ผู้ใช้ให้",
        },
    )
    assert response.status_code == 201, response.text
    publication = response.json()
    assert publication["caption"].endswith(f"🛒 พิกัดสินค้า กดดูตรงนี้: {affiliate_url}")
    assert publication["comment_text"].endswith(f"👉 กดสั่ง/ดูรายละเอียด: {affiliate_url}")
    project = product_client.get(f"/api/projects/{publication['project_id']}", headers=ORIGIN).json()
    assert project["product_details"] == "รายละเอียดและรีวิวที่ผู้ใช้ให้"
    assert project["affiliate_url"] == affiliate_url
    assert len(project["assets"]) == 2
    assert all(asset["kind"] == "post_image" for asset in project["assets"])
    assert len(publication["media_assets"]) == 2
    assert publication["render_asset"]["id"] == publication["media_assets"][0]["id"]
    assert publication["media_type"] == "image"


def test_retrying_image_post_save_reuses_the_same_draft(product_client):
    submission_id = str(uuid.uuid4())
    form = {
        "caption": "ชั้นวางเอกสารสำหรับโต๊ะทำงาน",
        "affiliate_url": "https://s.shopee.co.th/example",
        "submission_id": submission_id,
    }
    image = b"\x89PNG\r\n\x1a\npayload"
    first = product_client.post(
        "/api/image-posts", headers=ORIGIN,
        files={"image_files": ("shelf.png", image, "image/png")}, data=form,
    )
    assert first.status_code == 201, first.text

    repeated = product_client.post(
        "/api/image-posts", headers=ORIGIN,
        files={"image_files": ("shelf.png", image, "image/png")}, data=form,
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == first.json()["id"] == submission_id
    assert repeated.json()["project_id"] == first.json()["project_id"]
    assert len(repeated.json()["media_assets"]) == 1
    listed = product_client.get(f"/api/publications?project_id={first.json()['project_id']}", headers=ORIGIN)
    assert listed.status_code == 200, listed.text
    assert [post["id"] for post in listed.json()] == [submission_id]


def test_image_post_without_affiliate_link_keeps_user_caption_unchanged(product_client):
    caption = "ชั้นวางเอกสารสำหรับโต๊ะทำงาน\nพิกัด: https://s.shopee.co.th/manual"
    response = product_client.post(
        "/api/image-posts", headers=ORIGIN,
        files={"image_files": ("shelf.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
        data={"caption": caption, "comment_text": "", "auto_append_link": "false"},
    )
    assert response.status_code == 201, response.text
    post = response.json()
    assert post["caption"] == caption
    assert post["comment_text"] == ""
    assert post["affiliate_url"] is None


def test_image_post_auto_link_does_not_duplicate_a_manual_link(product_client):
    link = "https://s.shopee.co.th/example"
    caption = f"โต๊ะเรียบร้อยขึ้น\nพิกัด: {link}"
    response = product_client.post(
        "/api/image-posts", headers=ORIGIN,
        files={"image_files": ("shelf.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
        data={"caption": caption, "comment_text": "", "affiliate_url": link, "auto_append_link": "true"},
    )
    assert response.status_code == 201, response.text
    post = response.json()
    assert post["caption"] == caption
    assert post["caption"].count(link) == 1
    assert post["comment_text"].count(link) == 1


def test_editing_image_post_replaces_the_selected_original_file(product_client):
    created = product_client.post(
        "/api/image-posts",
        headers=ORIGIN,
        files=[
            ("image_files", ("first.jpg", b"\xff\xd8\xfffirst", "image/jpeg")),
            ("image_files", ("second.png", b"\x89PNG\r\n\x1a\nsecond", "image/png")),
        ],
        data={"caption": "โพสต์ภาพ", "affiliate_url": "https://s.shopee.co.th/example"},
    )
    assert created.status_code == 201, created.text
    publication = created.json()
    second_image = publication["media_assets"][1]
    with main_module.SessionLocal() as db:
        old_relative_path = db.get(main_module.Asset, second_image["id"]).relative_path
    replacement_bytes = b"\xff\xd8\xffreplacement-image"

    response = product_client.put(
        f"/api/publications/{publication['id']}/images/{second_image['id']}",
        headers=ORIGIN,
        files={"image_file": ("replacement.jpg", replacement_bytes, "image/jpeg")},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert [asset["id"] for asset in updated["media_assets"]] == [asset["id"] for asset in publication["media_assets"]]
    assert updated["media_assets"][1]["original_name"] == "replacement.jpg"
    assert updated["render_asset"]["id"] == publication["render_asset"]["id"]
    assert updated["events"][-1]["event_type"] == "image_replaced"
    downloaded = product_client.get(f"/api/assets/{second_image['id']}/file")
    assert downloaded.status_code == 200
    assert downloaded.content == replacement_bytes
    assert not main_module.resolve_media_path(old_relative_path).exists()


def test_image_copy_generation_sends_only_product_text_to_ai(product_client, monkeypatch):
    captured = {}

    def fake_generate_json(**kwargs):
        captured.update(kwargs)
        return ({"caption": "เสื้อดี 로우웨어 จนตู้เสื้อผ้าต้องเปิดทาง!", "comment_text": "ชอบแล้วกดไปส่องสีที่ใช่เลย"}, "gemini-test")

    monkeypatch.setattr(main_module, "get_gemini_json", fake_generate_json)
    product_info = "เสื้อคอตตอน สีดำและขาว ไซซ์ S–XL รอบอก 96–112 ซม."
    response = product_client.post(
        "/api/image-posts/generate-copy",
        headers=ORIGIN,
        data={"product_details": product_info, "affiliate_url": "https://s.shopee.co.th/copy-link"},
    )
    assert response.status_code == 200, response.text
    assert product_info in captured["prompt"]
    assert "ไม่ต้องกวน ไม่เล่นมุก ไม่ฮาร์ดเซล" in captured["prompt"]
    assert "เรียบเรียงใจความใหม่ให้อ่านลื่น" in captured["prompt"]
    assert "image_post_copy_v1" == captured["task"]
    assert "images" not in captured
    assert "https://s.shopee.co.th/copy-link" not in captured["prompt"]
    assert response.json() == {
        "caption": "😏 เสื้อดี จนตู้เสื้อผ้าต้องเปิดทาง!\n\n🛒 พิกัดสินค้า กดดูตรงนี้: https://s.shopee.co.th/copy-link",
        "comment_text": "🛒 ชอบแล้วกดไปส่องสีที่ใช่เลย\n\n👉 กดสั่ง/ดูรายละเอียด: https://s.shopee.co.th/copy-link",
        "model_name": "gemini-test",
    }


def test_image_copy_generation_works_without_link(product_client, monkeypatch):
    monkeypatch.setattr(
        main_module, "get_gemini_json",
        lambda **_kwargs: ({"caption": "ชั้นวางเอกสารช่วยจัดโต๊ะ", "comment_text": "ลองดูรายละเอียดสินค้า"}, "gemini-test"),
    )
    response = product_client.post(
        "/api/image-posts/generate-copy", headers=ORIGIN,
        data={"product_details": "ชั้นวางเอกสาร", "auto_append_link": "false"},
    )
    assert response.status_code == 200, response.text
    assert "https://" not in response.json()["caption"]
    assert "https://" not in response.json()["comment_text"]


def test_image_copy_generation_uses_attached_image_when_details_empty(product_client, monkeypatch):
    captured = {}

    def fake_generate_json(**kwargs):
        captured.update(kwargs)
        return ({"caption": "กล่องเก็บของมีล้อ เลื่อนมาจัดโต๊ะให้โล่ง", "comment_text": "ไปดูพิกัดกัน"}, "gemini-test")

    monkeypatch.setattr(main_module, "get_gemini_json", fake_generate_json)
    image = b"\x89PNG\r\n\x1a\n" + b"sample-image"
    response = product_client.post(
        "/api/image-posts/generate-copy", headers=ORIGIN,
        data={"product_details": "", "affiliate_url": "https://s.shopee.co.th/copy-link"},
        files=[("image_files", ("product.png", image, "image/png"))],
    )
    assert response.status_code == 200, response.text
    assert captured["images"] == [("image/png", image)]
    assert captured["task"] == "image_post_copy_v2"
    assert "อ่านข้อความที่มองเห็นในภาพให้ครบ" in captured["prompt"]
    assert "ผู้ใช้ไม่ได้กรอกข้อมูลสินค้า" in captured["prompt"]
    assert "https://s.shopee.co.th/copy-link" in response.json()["caption"]


def test_image_copy_generation_needs_details_or_image(product_client):
    response = product_client.post(
        "/api/image-posts/generate-copy", headers=ORIGIN,
        data={"product_details": "", "affiliate_url": "https://s.shopee.co.th/copy-link"},
    )
    assert response.status_code == 422
