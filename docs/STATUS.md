# สถานะพัฒนา

อัปเดต: 26 กันยายน 2026

## Phase 0–1: เครื่องมือ โปรเจกต์ และนำเข้าไฟล์ — เสร็จ

- React + TypeScript UI, FastAPI, SQLite/SQLAlchemy และ Alembic migrations
- สร้าง/ค้นหา/แก้โปรเจกต์ เก็บข้อมูลสินค้าและลิงก์ Affiliate
- อัปโหลดวิดีโอ/เพลง ตรวจชนิดไฟล์ ขนาด SHA-256 และอ่าน metadata ด้วย FFprobe
- เก็บไฟล์ต้นฉบับแยกจาก source code และมี durable job/event log พร้อมกู้คิวหลังปิดโปรแกรม
- Windows launcher, คู่มือเริ่มใช้ และ health/capability check
- Windows Setup `.exe`, ไอคอนโปรแกรม และ shortcut บน Desktop/Start Menu

## Phase 2: ตัดต่อในเครื่องโดยไม่พึ่ง AI — เสร็จ

- นำเข้า SRT, เพิ่ม/แก้เวลาและข้อความซับต้นฉบับ/ภาษาไทย และส่งออก SRT
- ตัวอย่างวิดีโอแสดงกรอบปิดทับ/ซับไทยตามเวลา
- ปรับตำแหน่งกรอบด้วยเปอร์เซ็นต์ สี ความทึบ และเวลา
- ปิดเสียงต้นฉบับ หรือเลือกเพลงจากไฟล์ในเครื่อง ปรับระดับเสียง/เฟด และวนเพลงสั้นให้ยาวเท่าวิดีโอ
- คิว render ผ่าน FFmpeg สร้าง MP4 ใหม่โดยไม่เขียนทับต้นฉบับ เก็บไฟล์และสถานะไว้ในโปรเจกต์
- ตรวจคลิปสังเคราะห์ 3 วินาที: ได้ MP4 360×640, ภาพมีซับไทยและกรอบตามตำแหน่ง, โหมด mute ไม่มี audio stream, โหมดเพลงมี audio stream และความยาวเท่า source

## Phase 3: OCR และ Gemini — ตัวเชื่อมพร้อม; ยืนยัน API จากภาพข้อผิดพลาดแล้ว แต่ยังไม่ทดสอบรุ่น 3.5 หลังแก้

- Windows DPAPI เก็บ API key แยกจาก SQLite/source และอ่านกลับเฉพาะฝั่ง backend
- หน้าตั้งค่าให้เลือก `gemini-3.5-flash-lite` (ค่าเริ่มต้น) หรือ `gemini-3.1-flash-lite`; เมื่อ 3.1 ตอบ 5xx จึงลอง 3.5 ซ้ำหนึ่งครั้ง แต่ไม่เปลี่ยนรุ่นเมื่อชนโควตา 429
- อ่านเฟรมตัวอย่างไม่เกิน 60 ภาพจากวิดีโอ ส่งไป OCR แบบมีโครงสร้าง สร้างซับร่าง/กรอบแนะนำ และต้องตรวจทาน
- คิวแปลซับเป็นชุด ตรวจว่า stable ID ไม่เปลี่ยน และ cache ผลลัพธ์ซ้ำตาม model/input
- คิวเขียนสคริปต์/แคปชั่น/คอมเมนต์; คำสั่งห้ามแต่งราคา/จุดขาย และแอปแนบ URL Affiliate ที่บันทึกไว้อย่างตรงตัว
- ปุ่มเชื่อม/ทดสอบเรียก Google เฉพาะเมื่อผู้ใช้กด; UI แจ้งข้อมูลที่ส่งและข้อควรระวังของ Free Tier

สถานะเครื่องนี้: ภาพล่าสุดแสดงการเรียก API จริง โดย 3.1 ตอบ 503 และรุ่นสำรอง 2.5 ถูกปฏิเสธเพราะบัญชีใหม่ใช้ไม่ได้; ยังไม่ได้ยืนยันการเชื่อมต่อหลังเปลี่ยนรุ่นสำรองเป็น 3.5 หรือทดสอบ HTTP 429, structured output และ OCR กับคลิปจริง; ตัวคีย์ไม่อยู่ใน source, เอกสาร หรือ package

## Phase 4: รายการโพสต์และคิวเวลา — เตรียมงานในเครื่องได้แล้ว

- สร้างดราฟต์จาก MP4 ที่เรนเดอร์สำเร็จใน revision เดียวกันเท่านั้น
- บันทึก snapshot ของวิดีโอ แคปชั่น คอมเมนต์ และลิงก์ Affiliate; ลิงก์ถูกแนบซ้ำให้ตรงกับข้อมูลสินค้า และข้อมูลโพสต์ไม่เปลี่ยนตามการแก้โปรเจกต์ภายหลัง
- หน้า “รายการโพสต์” มีตัวกรองดราฟต์/ตั้งเวลา/กำลังส่ง/กำลังประมวลผล/ต้องดำเนินการ/เผยแพร่แล้ว/ยกเลิก แสดงวิดีโอ ลิงก์ เวลา สถานะคอมเมนต์ และประวัติ
- แก้แคปชั่น/คอมเมนต์ ตั้งเวลา ยกเลิก และเก็บสถานะผ่าน SQLite; worker ตรวจเวลาที่ถึงกำหนดหลังเปิดโปรแกรมใหม่ได้
- หลังเชื่อมเพจ สามารถโพสต์ทันทีหรือเข้าคิวเวลา; ถ้าขาด token, ไฟล์ หรือคลิปไม่ผ่าน Reel preflight ระบบขึ้น “ต้องดำเนินการ”
- ถ้าโปรแกรมกลับมาทำงานช้ากว่ากำหนดเกิน 10 นาที จะไม่โพสต์ย้อนหลังเอง ต้องตั้งเวลาใหม่หรือกดโพสต์เอง

ข้อจำกัด: ยังไม่มี token/เพจทดสอบ จึงยังไม่ยืนยันการทำงานกับ Meta จริง

## Phase 5: Facebook Pages — connector พร้อม แต่ยังไม่ทดสอบ live

- Settings รองรับ Page ID + Page Access Token, ตรวจชื่อเพจกับ Graph API และเก็บ token ต่อเพจด้วย Windows DPAPI
- Graph API adapter ทำขั้น Reels start/upload/finish, poll status, คอมเมนต์หลัง publish และบันทึก remote IDs
- ตรวจวิดีโอ 9:16, 540×960+, 23 FPS+, 4–60 วินาที ก่อนจัดคิว Reels
- recover/reconcile ไม่ส่งซ้ำอัตโนมัติเมื่อคำสั่ง external กำกวม; คอมเมนต์มีสถานะแยกและลองใหม่ได้เฉพาะเมื่อ Meta ปฏิเสธคำขอชัดเจน
- ตรวจด้วย mock provider (ไม่ยิง Meta): ตั้งคิว → publish → status complete → comment success, token protection และ event log ทำงานครบ

ข้อจำกัด: ยังไม่มี Page token หรือเพจทดสอบ; ไม่ได้เรียก Graph API จริง จึงยังไม่ยืนยัน permission/app review, token lifecycle, `v26.0`, URL ของโพสต์ หรือสถานะการประมวลผลกับเพจจริง ต้องให้ผู้ใช้ใส่ token ในหน้าตั้งค่าเอง

## Phase 6: ความทนทานและแจกใช้งาน — บางส่วน

- launcher, migrations, file storage, health checks และ restart recovery มีแล้ว
- หน้า Settings ดาวน์โหลด backup ZIP ซึ่งทำ SQLite online snapshot รวมฐานข้อมูลและ media โดยไม่รวม DPAPI secrets; response ลบไฟล์ชั่วคราวหลังดาวน์โหลด
- `scripts/restore.ps1` เรียกตัวตรวจ/กู้คืนแบบออฟไลน์ ตรวจ path ใน ZIP, symlink, manifest, SQLite integrity และ schema version ก่อนแทนข้อมูล ป้องกันการกู้คืนขณะแอปยังเปิดอยู่ ขอพิมพ์ `RESTORE` และเก็บ rollback backup ของฐานข้อมูล/media ปัจจุบันก่อน
- ตอนเริ่มแอปล้างเฉพาะไฟล์อัปโหลด/OCR/render ชั่วคราวที่เก่ากว่า 24 ชั่วโมง
- `scripts/package.py` สร้าง Windows portable ZIP พร้อม launcher และ frontend ที่ build แล้ว; แตกลงโฟลเดอร์เครื่องแล้วเปิดผ่าน `Start Studio.vbs` เพื่อเข้าหน้าต่างแอปโดยตรง
- GitHub Release updater แสดงหมายเลขเวอร์ชัน/Release notes, ดาวน์โหลดไฟล์จาก repo Public, ตรวจ SHA-256 และอัปเดตตาม allowlist ที่ไม่รวม Data/Backups; บล็อกการอัปเดตเมื่อมีงานค้าง
- `.github/workflows/publish-release.yml` รันทดสอบ backend, build frontend และเผยแพร่ ZIP พร้อม checksum เมื่อ push tag `v*` ที่ตรงกับ `app_version`
- ยังเหลือทดสอบติดตั้ง, restore และอัปเดต end-to-end บนเครื่องสะอาดจริง; package ยังต้องใช้ Python, FFmpeg/FFprobe และอินเทอร์เน็ตเพื่อติดตั้ง Python dependencies ครั้งแรก

## การตรวจที่ทำในเครื่อง

- `backend\.venv\Scripts\python.exe -m compileall -q app` ผ่าน
- Backend suite: 10 passed; มี deprecation warnings จาก Starlette/httpx test client
- `frontend`: `npm run build` ผ่าน TypeScript และ Vite
- Mock-provider smoke: เชื่อมเพจด้วย Graph verification ที่จำลอง, คิว Reel, ยืนยัน status และคอมเมนต์จนได้ `published/published`; ไม่มีการยิง Meta จริง
- Render smoke จริงผ่าน FFmpeg ทั้ง mute และ short-music loop; ตรวจภาพเฟรมแล้วเห็นภาษาไทยและกรอบปิดทับ
- ทดสอบ FFmpeg frame sampling ได้ 2 ภาพจากคลิปสังเคราะห์ 3 วินาที
- ทดสอบ DPAPI round-trip ด้วยคีย์จำลองใน data directory ชั่วคราว และลบคีย์ทดสอบแล้ว
- Backup API test ยืนยัน ZIP มีฐานข้อมูล ไม่มี secret และปฏิเสธ cross-site request; restore smoke test ใช้ data directory ชั่วคราว ยืนยัน path traversal ถูกปฏิเสธและโฟลเดอร์ secrets เดิมถูกเก็บไว้
- Portable ZIP รุ่นก่อน updater: 59 entries, 3.90 MB; CRC ผ่าน และตรวจว่าไม่มี `.venv`, `node_modules` หรือ DPAPI secret files

## งานถัดไป

1. ปรับ API keys ให้ผู้ใช้ใส่ Gemini key แล้วทดสอบ OCR/แปล/เขียนข้อความกับคลิปที่มีสิทธิ์ใช้งาน
2. เมื่อผู้ใช้ตั้งค่า Page ID/token ให้ทดสอบแบบอ่านเพจ จากนั้นอนุญาต/ตรวจรายละเอียดโพสต์หนึ่งรายการก่อนทดสอบ live
3. เพิ่มการต่ออายุ token, หน้าเลือกเพจรายโพสต์, video feed posts และ recovery/reconcile ที่ละเอียดขึ้นตามผลทดสอบ live
4. ตรวจการติดตั้ง/กู้คืน portable ZIP บน Windows เครื่องสะอาด
