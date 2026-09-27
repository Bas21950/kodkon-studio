import pytest
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


def test_caption_prompt_requires_detailed_copy_grounded_in_the_single_info_field():
    product_info = "เสื้อคอตตอน สีดำ/ขาว ไซซ์ S–XL รอบอก 96–112 ซม. รีวิว 4.8/5"
    prompt = product_copy_prompt({"product_info": product_info}, "caption")
    assert product_info in prompt
    assert "ยึดประเภทสินค้าและข้อเท็จจริงตามนั้น" in prompt
    assert "8–14 บรรทัด" in prompt
    assert "วัสดุ ขนาด วิธีใช้" in prompt
    assert "ห้ามใส่ URL ใน caption" in prompt


def test_image_caption_prompt_paraphrases_key_facts_with_hard_sell_thai_tone():
    product_info = "เสื้อยืดผ้าคอตตอน ไซซ์ S–XL มีดำและขาว ลด 20% โอนก่อนเท่านั้น ส่งช้า"
    prompt = image_post_copy_prompt(product_info)
    assert product_info in prompt
    assert "กวน แสบ มั่นใจ แหวกแนว" in prompt
    assert "ปิดการขายแบบสั่งตรง ๆ ไม่อ้อมค้อม" in prompt
    assert "ต้องมีมุกหรือประโยคแซว" in prompt
    assert "ห้ามทำให้โทนอ่อนลงเป็นรีวิวเรียบ ๆ" in prompt
    assert "ห้ามใช้คอมเมนต์กลาง ๆ" in prompt
    assert "3–5 ตัวกระจายตามบรรทัด" in prompt
    assert "อิโมจิ 1–2 ตัว" in prompt
    assert "ห้ามมีอักษรเกาหลี ญี่ปุ่น" in prompt
    assert "ความยาวเนื้อหาอย่างน้อยประมาณ 220 ตัวอักษร" in prompt
    assert "ห้ามคัดประโยคหรือย่อหน้าจากต้นฉบับมาวางตรง ๆ" in prompt
    assert "เลือกเฉพาะ 2–4 จุด" in prompt
    assert "ตัดแฮชแท็กที่แปะมาเป็นพรืด" in prompt
    assert "ห้ามแต่งสเปก คะแนนรีวิว" in prompt


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
        json={"product_details": product_info, "affiliate_url": "https://s.shopee.co.th/copy-link"},
    )
    assert response.status_code == 200, response.text
    assert product_info in captured["prompt"]
    assert "ต้องมีมุกหรือประโยคแซว" in captured["prompt"]
    assert "ห้ามคัดประโยคหรือย่อหน้าจากต้นฉบับมาวางตรง ๆ" in captured["prompt"]
    assert "image_post_copy_v1" == captured["task"]
    assert "images" not in captured
    assert "https://s.shopee.co.th/copy-link" not in captured["prompt"]
    assert response.json() == {
        "caption": "😏 เสื้อดี จนตู้เสื้อผ้าต้องเปิดทาง!\n\n🛒 พิกัดสินค้า กดดูตรงนี้: https://s.shopee.co.th/copy-link",
        "comment_text": "🛒 ชอบแล้วกดไปส่องสีที่ใช่เลย\n\n👉 กดสั่ง/ดูรายละเอียด: https://s.shopee.co.th/copy-link",
        "model_name": "gemini-test",
    }
