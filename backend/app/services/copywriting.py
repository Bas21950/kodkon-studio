from __future__ import annotations


def append_discount_offer(text: str, discount_text: str | None) -> str:
    """Append only the discount explicitly supplied by the user."""
    offer = " ".join((discount_text or "").split())
    content = text.strip()
    if not offer:
        return content
    line = f"🎟️ โปรโมชัน: {offer}"
    if line.casefold() in content.casefold():
        return content
    return f"{content}\n\n{line}" if content else line


def append_review_analysis(text: str, review_score: float, review_summary: str) -> str:
    """Add a clearly labeled AI estimate only when review evidence exists."""
    content = text.strip()
    summary = " ".join((review_summary or "").split())[:260]
    if not 0 < review_score <= 5 or not summary:
        return content
    line = f"⭐ สรุปจากรีวิว: {summary} · คะแนนวิเคราะห์ AI {review_score:.1f}/5 (ไม่ใช่คะแนนทางการ)"
    if "คะแนนวิเคราะห์ AI" in content:
        return content
    return f"{content}\n\n{line}" if content else line


def append_product_rating(text: str, rating: float | None, review_count: int | None) -> str:
    """Append the exact rating read from a product page, never an AI estimate."""
    content = text.strip()
    if rating is None or not 0 < rating <= 5:
        return content
    if "คะแนนเฉลี่ยหน้าสินค้า" in content:
        return content
    count = f" จาก {review_count:,} รีวิว" if review_count and review_count > 0 else ""
    line = f"⭐ คะแนนเฉลี่ยหน้าสินค้า {rating:.1f}/5{count}"
    return f"{content}\n\n{line}" if content else line


def normalize_product_rating(value) -> float | None:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 < rating <= 5:
        return None
    return round(rating, 1)


def normalize_product_review_count(value) -> int | None:
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or count <= 0 or count > 100_000_000:
        return None
    return count
