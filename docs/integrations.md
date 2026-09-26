# สถานะการเชื่อมบริการภายนอก

อัปเดตตรวจเอกสาร: 24 กันยายน 2026

## Gemini

สถานะ: เขียนตัวเชื่อม REST, คิวงาน, cache, หน้าตั้งค่า และส่วนจัดเก็บคีย์แล้ว ภาพข้อผิดพลาดล่าสุดยืนยันว่าเรียก API แล้ว แต่ยังไม่ได้ทดสอบ `gemini-3.5-flash-lite` หลังแก้ไข

ค่าเริ่มต้นใช้ `gemini-3.5-flash-lite`; เลือก `gemini-3.1-flash-lite` ได้ด้วย ทั้งคู่มีราคา Free Tier ในเอกสาร Google ปัจจุบัน หาก 3.1 ตอบข้อผิดพลาดฝั่งบริการ (5xx) จึงลอง 3.5 ให้อัตโนมัติหนึ่งครั้ง ส่วน 429/โควตาจะไม่สลับรุ่นและให้ผู้ใช้ลองใหม่ภายหลัง โมเดล 2.5 ถูกนำออกจากรายการ เพราะ Google จำกัดการเข้าถึงสำหรับผู้ใช้ที่ยังไม่เคยใช้งานโมเดล 2.5 มาก่อน การเข้าถึงและโควตาจริงยังขึ้นกับโปรเจกต์/บัญชี

API key ถูกปกป้องด้วย Windows DPAPI ใต้บัญชี Windows ปัจจุบัน ไม่เก็บใน SQLite, source, backup หรือ log และแสดงได้เฉพาะสถานะว่ามีคีย์เท่านั้น เมื่อผู้ใช้สั่ง OCR จะส่งภาพเฟรมตัวอย่างไป Google; เมื่อสั่งแปล/เขียนข้อความจะส่งเฉพาะข้อมูลที่เกี่ยวข้อง เอกสาร Free Tier ของ Google ระบุว่า prompt/response อาจถูกใช้เพื่อปรับปรุงผลิตภัณฑ์ จึงมีการแจ้งในหน้าตั้งค่า ห้ามป้อนข้อมูลส่วนตัวหรือข้อมูลลับ

ไม่มีการเรียก Gemini อัตโนมัติเมื่อเปิดโปรแกรม การเรียกจาก UI ต้องเกิดจากผู้ใช้กด “อ่านซับ”, “แปลเป็นไทย”, “เขียนด้วย Gemini” หรือ “ทดสอบการเชื่อมต่อ” เท่านั้น ผล OCR/คำแปลเป็นฉบับร่างที่ต้องตรวจทานก่อนใช้

## Facebook Pages

สถานะ: มี connector, หน้าตั้งค่า, worker และ state tracking สำหรับ Facebook Reels/คอมเมนต์แล้ว แต่ยังไม่มี token หรือเพจทดสอบ จึงยังไม่ได้เรียก Graph API จริง

### การเชื่อมต่อและขอบเขต

- ผู้ใช้ใส่ Page ID และ Page Access Token ที่ได้จาก Meta Graph API Explorer เอง; โปรแกรมตรวจชื่อ Page ด้วย token ก่อนเก็บ
- token ถูกเข้ารหัสด้วย Windows DPAPI แยกไฟล์ต่อเพจ ไม่เก็บใน SQLite, source, logs หรือ API response; ชื่อเพจ/Page ID และสถานะเลือกเพจเก็บใน SQLite
- ต้องมี `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `pages_manage_engagement`; ผู้สร้าง token ต้องมีงาน Page ที่ใช้สร้างเนื้อหาและดูแลคอมเมนต์ การอนุมัติสิทธิ์ของ Meta ขึ้นกับ app/account
- API version ค่าเริ่มต้น `v26.0`; กำหนดรุ่นอื่นได้ด้วย `KODKON_FACEBOOK_API_VERSION` ก่อนเปิดโปรแกรม
- ตั้งเวลาแล้ว worker โพสต์อัตโนมัติเมื่อโปรแกรมทำงาน; ถ้าเลยกำหนดเกิน 10 นาทีหลังเครื่องปิด จะหยุดเป็น “ต้องดำเนินการ” และไม่ปล่อยโพสต์รวดเดียวหลังเปิดเครื่อง
- ตอนนี้รองรับ Facebook Reels เท่านั้น ตรวจ MP4 แนวตั้ง 9:16, อย่างน้อย 540×960, 23 FPS, ความยาว 4–60 วินาทีก่อนส่ง
- หลังสร้าง Reel จะตรวจ status จาก Meta ก่อนคอมเมนต์; สถานะโพสต์และคอมเมนต์แยกกัน คอมเมนต์จะทำหลังยืนยัน Reel แล้วเท่านั้น
- ถ้าผลการส่ง/คอมเมนต์ไม่ชัดเจน ระบบจะไม่ลองซ้ำอัตโนมัติและบันทึก remote ID/เหตุการณ์ให้ตรวจ หาก Meta ปฏิเสธคอมเมนต์ชัดเจน จึงมีปุ่มลองคอมเมนต์ซ้ำแยกจากโพสต์

ยังไม่ได้ตรวจ App Review, token หมดอายุ, สิทธิ์จริง, การตอบกลับจริงของ `v26.0`, การประมวลผลวิดีโอจริง หรือการเผยแพร่บนเพจผู้ใช้ ต้องเชื่อมเพจและตรวจรายละเอียดรายการก่อนใช้จริง ไม่มีการเรียก Meta จากการพัฒนาครั้งนี้

## เอกสารเริ่มต้น

- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Gemini rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Gemini API generateContent REST: https://ai.google.dev/api/generate-content
- Gemini billing tiers and data use: https://ai.google.dev/gemini-api/docs/billing
- Gemini model IDs: https://ai.google.dev/gemini-api/docs/models
- Meta Facebook API collection: https://www.postman.com/meta/facebook
- Meta Graph API Explorer: https://developers.facebook.com/tools/explorer/
- Meta Reels Publishing: https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api
- Meta Graph API Comments: https://developers.facebook.com/docs/graph-api/reference/object/comments/
- FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
