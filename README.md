# กดก่อนคิดทีหลัง Studio

โปรแกรมในเครื่องสำหรับเก็บโปรเจกต์วิดีโอสินค้า แก้ซับไทย/นำเข้า SRT ปิดซับเดิมด้วยกรอบสีทึบ เลือกเพลงหรือปิดเสียงต้นฉบับ เรนเดอร์ MP4 ใช้ Gemini Free Tier สำหรับ OCR/แปล/เขียนข้อความ และเตรียมดราฟต์/คิวเวลาโพสต์พร้อมลิงก์ Affiliate

## ติดตั้งจาก GitHub Release

ดาวน์โหลด `kodkon-studio-<version>-windows-portable.zip` จาก Releases แล้วแตกไฟล์ทั้งหมดลงโฟลเดอร์ที่ต้องการ จากนั้นดับเบิลคลิก `Start Studio.bat` ข้อมูลจะอยู่ในโฟลเดอร์ `Data` ข้าง ๆ และไม่อยู่ใน ZIP; เมื่อติดตั้งทับชุดเดิม อย่าลบ `Data` หรือ `Backups`

## ความต้องการเครื่อง

- Windows 10/11 64-bit
- Python 3.11 ขึ้นไป (ทดสอบเบื้องต้นกับ Python 3.14.4)
- Node.js 22.12 ขึ้นไปเฉพาะเมื่อ build หน้าจอจาก source (ทดสอบเบื้องต้นกับ Node 24.13.0); portable ZIP ใช้หน้าจอที่ build ไว้แล้ว
- FFmpeg และ FFprobe อยู่ใน PATH
- อินเทอร์เน็ตใช้ติดตั้ง dependencies และเมื่อต้องการเรียก Gemini

## เปิดโปรแกรมครั้งแรก

1. เปิด PowerShell ในโฟลเดอร์โปรเจกต์นี้
2. อนุญาตให้สคริปต์ทำงานในหน้าต่างปัจจุบันเฉพาะเมื่อ Windows ปิดการทำงานของสคริปต์: `Set-ExecutionPolicy -Scope Process Bypass`
3. รัน `./scripts/start.ps1`
4. สคริปต์สร้าง Python virtual environment, ติดตั้งแพ็กเกจ และเปิดเซิร์ฟเวอร์ที่ `http://127.0.0.1:8765`; จะ build หน้าจอเมื่อไม่มี build พร้อมใช้หรือ source ใหม่กว่า
5. กด Ctrl+C ในหน้าต่าง PowerShell เพื่อปิดโปรแกรม

เมื่อใช้ portable ZIP ไม่ต้องติดตั้ง Node.js; ต้องมี Python และ FFmpeg/FFprobe ตามข้อกำหนด สคริปต์ติดตั้ง Python dependencies ให้เมื่อเริ่มครั้งแรก

## สร้าง portable ZIP จาก source

หลัง build หน้าจอแล้ว รัน `python scripts/package.py` จากโฟลเดอร์โปรเจกต์ ไฟล์จะอยู่ใน `release/` และไม่มี environment, ข้อมูลใน `%LOCALAPPDATA%` หรือ DPAPI secrets รวมอยู่

## ตรวจสอบและติดตั้งอัปเดต

ชุดติดตั้งในเครื่องนี้ใช้ `Start Studio.bat` จากโฟลเดอร์ติดตั้งเพื่อส่งตำแหน่งโปรแกรมให้ตัวอัปเดต ในหน้า “ตั้งค่าโปรแกรม” กด “ตรวจสอบอัปเดต” เพื่ออ่านเวอร์ชันและ Release notes จาก GitHub; หากมีเวอร์ชันใหม่ กด “ดาวน์โหลดและติดตั้ง” โปรแกรมจะตรวจ SHA-256 ปิดแล้วเปิดใหม่เอง อัปเดตเฉพาะโค้ดใต้ `App\KodKon Studio` และไม่แตะโฟลเดอร์ `Data` การเผยแพร่ทำโดย push tag ที่ตรงกับ `app_version` เช่น `v0.2.0`; GitHub Actions จะทดสอบ สร้าง ZIP และเผยแพร่ Release notes

## เปิดแบบพัฒนา

ติดตั้ง backend/frontend ตามคำสั่งใน scripts/start.ps1 แล้วเปิดสองหน้าต่าง PowerShell:

- หน้าต่าง backend: เข้าโฟลเดอร์ `backend`, ใช้ `..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765` เมื่อรันจาก root หรือ `\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765` เมื่ออยู่ใน backend
- หน้าต่าง frontend: เข้า `frontend`, รัน `npm run dev`, แล้วเปิด `http://127.0.0.1:5173`

อย่าเพิ่ม `--reload` ระหว่างงานที่มี worker เพราะการ reload จะหยุดและเริ่ม worker ใหม่

## ข้อมูลส่วนตัวและที่เก็บไฟล์

ค่าเริ่มต้นเก็บฐานข้อมูล งาน และไฟล์วิดีโอที่ `%LOCALAPPDATA%\KodKonStudio` แยกจาก source code ตั้งค่าโฟลเดอร์อื่นได้ด้วย environment variable `KODKON_DATA_DIR` ก่อนเปิดโปรแกรม ต้นฉบับไม่ถูกเขียนทับ

หน้า “ตั้งค่าโปรแกรม” มีปุ่มดาวน์โหลดไฟล์สำรอง ZIP ซึ่งรวมฐานข้อมูลและไฟล์สื่อ โดยไม่รวม Gemini API key และ Facebook Page token การกู้คืนต้องปิดโปรแกรมก่อน แล้วรัน `scripts/restore.ps1 -BackupPath "C:\path\backup.zip"`; ตัวกู้คืนตรวจ ZIP/ฐานข้อมูลก่อน สร้างสำเนาข้อมูลปัจจุบันไว้ย้อนกลับ และขอให้พิมพ์ `RESTORE` ก่อนแทนที่ ดูขั้นตอนเต็มที่ `docs/backup-restore.md`

เมื่อเปิดโปรแกรม ระบบล้างเฉพาะไฟล์ชั่วคราวของอัปโหลด/OCR/render ที่ค้างเกิน 24 ชั่วโมง ไม่แตะต้นฉบับหรือผลลัพธ์ที่สำเร็จ

API bind เฉพาะ 127.0.0.1 ไฟล์วิดีโอและฐานข้อมูลเก็บในเครื่อง ส่วนการเรียก OCR/แปล/เขียนข้อความจะส่งภาพตัวอย่างหรือข้อความที่เกี่ยวข้องไปยัง Google Gemini เมื่อผู้ใช้กดสั่งเท่านั้น API key ปกป้องด้วย Windows DPAPI และไม่แสดงกลับในโปรแกรม เอกสาร Free Tier ระบุว่า prompt/response อาจนำไปใช้ปรับปรุงผลิตภัณฑ์

หน้า “รายการโพสต์” เก็บวิดีโอ แคปชั่น ลิงก์ Affiliate คอมเมนต์ และเวลาที่ตั้งไว้ในเครื่อง เชื่อม Facebook Page ได้จากเมนูตั้งค่าด้วย Page ID และ Page Access Token; token เข้ารหัสใน Windows DPAPI โปรแกรมรองรับ Reels และคอมเมนต์หลังโพสต์ยืนยันสำเร็จเท่านั้น ถ้าเครื่องปิดเลยกำหนดเกิน 10 นาที ระบบจะหยุดให้ตรวจแทนการโพสต์ย้อนหลังเอง

ยังไม่มี token/เพจทดสอบในสภาพแวดล้อมพัฒนา จึงตรวจ flow ด้วย mock provider เท่านั้น ก่อนใช้งานจริงให้เชื่อมเพจและทดสอบกับคลิป/แคปชั่นของคุณเอง ดูข้อกำหนดสิทธิ์และสถานะตรวจจริงที่ `docs/integrations.md` และ `docs/STATUS.md`

## ตรวจและ build

Backend จาก `backend`:

    .\.venv\Scripts\python.exe -m pytest

Frontend จาก `frontend`:

    npm ci
    npm run build

`docs/STATUS.md` บอกงานที่ทำแล้ว/ยังไม่ได้ทดสอบ `docs/integrations.md` บอกสถานะ Gemini/Facebook
