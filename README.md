# 🧠 AI-900 Mock Test Bot

DOCX / PDF fayllardagi test savollarini avtomatik o'qib, ularni Telegram'da **quiz (poll)** ko'rinishida yuboruvchi bot. Foydalanuvchi savollarni 50 tadan iborat qismlar (chunk) bilan yechadi, statistikasi saqlanadi.

Bot interfeysi **o'zbek tilida**.

---

## 📋 Mundarija

- [Imkoniyatlar](#-imkoniyatlar)
- [Arxitektura](#-arxitektura)
- [Talablar](#-talablar)
- [O'rnatish](#-ornatish)
- [Sozlash (.env)](#-sozlash-env)
- [Savollarni yuklash](#-savollarni-yuklash)
- [Ishga tushirish](#-ishga-tushirish)
- [Komandalar](#-komandalar)
- [Fayl formatlari](#-fayl-formatlari)
- [Ma'lumotlar bazasi](#-malumotlar-bazasi)
- [Deploy (Railway / Heroku)](#-deploy-railway--heroku)
- [Loyiha tuzilishi](#-loyiha-tuzilishi)
- [Tez-tez uchraydigan muammolar](#-tez-tez-uchraydigan-muammolar)

---

## ✨ Imkoniyatlar

- 📥 **DOCX va PDF** fayllardan savollarni avtomatik parsing qilish
- 🎯 Telegram **native quiz poll** (to'g'ri javob bot tomonidan belgilanadi)
- 🔢 Test boshida **savol sonini tanlash**: 10 / 20 / 50 / Hammasi
- ✅ **To'g'ri va noto'g'ri** javoblarni real vaqtda kuzatish + foiz natija
- 📦 Savollar **50 tadan** qismlarga bo'lib beriladi (chunk tizimi)
- 🔀 Har bir testda savollar **tasodifiy** tartibda tanlanadi
- 📊 Har bir foydalanuvchi uchun **statistika** (testlar, to'g'ri/noto'g'ri, o'rtacha)
- 🧹 Savollarni **deduplikatsiya** qilish (takrorlanmaslik)
- 🔐 **Admin-only** komandalar (savol yuklash, hisoblash)
- 💾 Hech qanday tashqi baza kerak emas — **SQLite** (bitta fayl)

---

## 🏗 Arxitektura

```
                ┌──────────────┐
   DOCX / PDF   │   parser.py  │   parse_file()
   (docs/)  ──► │  DOCX/PDF →  │ ──────────────┐
                │   dict list  │               │
                └──────────────┘               ▼
                                       ┌──────────────┐
                                       │ database.py  │  questions.db (SQLite)
   Telegram      ┌──────────────┐      │  save / get  │
   foydalanuvchi │    bot.py    │ ◄──► │  stats       │
        ◄──────► │  handlers,   │      └──────────────┘
                 │  sessions,   │
                 │  quiz poll   │   sessions[user_id] (RAM)
                 └──────────────┘
```

Uchta modul:

| Fayl          | Vazifasi                                                                 |
| ------------- | ------------------------------------------------------------------------ |
| `bot.py`      | Telegram handlerlar, sessiya boshqaruvi, quiz poll yuborish, navigatsiya |
| `database.py` | SQLite bilan ishlash: savollar va foydalanuvchi statistikasi             |
| `parser.py`   | DOCX/PDF fayllarni o'qib, savollarni `dict` ro'yxatiga aylantirish       |

---

## 📦 Talablar

- **Python 3.11** (`runtime.txt` da `3.11.9` ko'rsatilgan)
- Telegram bot tokeni (`@BotFather` orqali olinadi)

### Python kutubxonalari

`requirements.txt` da hozircha faqat ikkita asosiy kutubxona bor:

```
python-telegram-bot==21.6
python-dotenv==1.0.1
```

> ⚠️ **Muhim:** `parser.py` qo'shimcha ravishda `python-docx` (DOCX uchun) va `pdfplumber` (PDF uchun) kutubxonalaridan foydalanadi. Agar siz `/load` komandasi orqali fayl yuklamoqchi bo'lsangiz, ularni ham o'rnating:
>
> ```
> python-docx
> pdfplumber
> ```
>
> Tavsiya: bularni `requirements.txt` ga qo'shib qo'ying. Faqat `/test` ni ishlatib, bazadagi tayyor savollar bilan ishlasangiz, bu kutubxonalar shart emas.

---

## 🚀 O'rnatish

```bash
# 1. Loyiha papkasiga kiring
cd microsoft-mock

# 2. Virtual muhit yarating (tavsiya etiladi)
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell)
# source .venv/bin/activate   # macOS / Linux

# 3. Kutubxonalarni o'rnating
pip install -r requirements.txt
pip install python-docx pdfplumber   # fayl yuklash uchun (ixtiyoriy)
```

---

## ⚙️ Sozlash (.env)

Loyiha papkasida `.env` fayl yarating:

```env
BOT_TOKEN=123456789:ABCdef_yourBotTokenHere
ADMIN_ID=987654321
```

| O'zgaruvchi | Majburiy | Tavsifi                                                                                   |
| ----------- | :------: | ----------------------------------------------------------------------------------------- |
| `BOT_TOKEN` |    ✅     | `@BotFather` dan olingan bot tokeni                                                        |
| `ADMIN_ID`  |    ➖     | Admin'ning Telegram user ID raqami. `/load` va `/count` faqat shu ID uchun ishlaydi. Standart: `0` |

> 💡 O'zingizning Telegram ID'ingizni bilish uchun [@userinfobot](https://t.me/userinfobot) ga yozing.

`.env` fayli `.gitignore` ga kiritilgan — token hech qachon git'ga tushmaydi.

---

## 📥 Savollarni yuklash

1. Loyiha papkasida `docs/` papkasini yarating (bot ham avtomatik yaratadi).
2. Savol fayllaringizni (`.docx` yoki `.pdf`) shu papkaga joylang.
3. Botda admin sifatida `/load` komandasini yuboring.

Bot har bir faylni parsing qiladi, deduplikatsiya qiladi va `questions.db` ga saqlaydi. Natijada nechta savol yuklanganini hisobot qilib qaytaradi:

```
📥 Yuklash yakunlandi

✅ ai900-tutor.docx — 142 ta savol
✅ ai900-explained.pdf — 88 ta savol

📦 Jami: 230 ta savol
```

> ♻️ Bir xil `source_file` nomi bilan qayta yuklasangiz, eski savollar o'chirilib, yangilari yoziladi (idempotent).

---

## ▶️ Ishga tushirish

```bash
python bot.py
```

Konsolda `Bot ishga tushdi...` chiqsa, bot **polling** rejimida ishlamoqda. Telegram'da botga `/start` yuboring.

---

## 💬 Komandalar

### Foydalanuvchi komandalari

| Komanda     | Tavsifi                                                                            |
| ----------- | --------------------------------------------------------------------------------- |
| `/start`    | Salomlashish + savol sonini tanlash tugmalari (10 / 20 / 50 / Hammasi)             |
| `/test`     | Savol sonini tanlash tugmalarini ko'rsatadi                                        |
| `/test 30`  | Tugmalarsiz, to'g'ridan-to'g'ri **30 ta** tasodifiy savol (istalgan son)            |
| `/stop`     | Aktiv testni to'xtatish (ishlangan savollar va natija saqlanadi)                   |
| `/stats`    | Shaxsiy statistika: testlar soni, to'g'ri/noto'g'ri, o'rtacha foiz                 |

### Admin komandalari (faqat `ADMIN_ID`)

| Komanda  | Tavsifi                                                  |
| -------- | -------------------------------------------------------- |
| `/load`  | `docs/` papkasidagi DOCX/PDF fayllarni bazaga yuklash    |
| `/count` | Bazadagi savollar umumiy sonini ko'rsatish               |

### Quiz oqimi (flow)

1. `/start` yoki `/test` → bot **savol sonini tanlash** tugmalarini ko'rsatadi (10 / 20 / 50 / Hammasi).
2. Foydalanuvchi sonni tanlaydi → shuncha tasodifiy savol bilan test boshlanadi.
3. Har bir savol **quiz poll** sifatida yuboriladi + "➡️ Keyingisi" / "🛑 Tugatish" tugmalari.
4. Foydalanuvchi javob beradi → "Keyingisi" ni bosadi.
5. (Agar > 50 savol bo'lsa) 50 ta tugagach → "✅ N-qism yakunlandi" + oraliq natija + "▶️ Keyingi 50 ta savol" tugmasi.
6. Barcha savollar tugagach → **yakuniy natija**: to'g'ri, noto'g'ri, javobsiz va foiz.

```
🏁 Test to'liq yakunlandi!

📝 Jami savollar: 20
✅ To'g'ri: 16
❌ Noto'g'ri: 3
⏭ Javobsiz: 1
🎯 Natija: 84%
```

> ℹ️ **Qanday ishlaydi:** Quiz poll'lar `is_anonymous=False` rejimida yuboriladi. Bot har bir poll'ni ro'yxatga oladi va `PollAnswerHandler` orqali foydalanuvchining tanlovini to'g'ri javob bilan solishtirib, **to'g'ri/noto'g'ri**ni sanaydi. Javob berilmagan (lekin "Keyingisi" bosilgan) savollar **javobsiz** deb hisoblanadi.

---

## 📄 Fayl formatlari

`parser.py` ikki formatni qo'llab-quvvatlaydi:

### 1. DOCX (tutor edition) — `parse_tutor_docx()`

Har bir savol bloki quyidagicha tuzilgan bo'lishi kerak:

```
Q1  (yangi savol boshlanishi — "Q" + raqam + bo'sh joy)
EN  What is the question text in English?
A) Variant A
B) Variant B
C) Variant C
D) Variant D
```

Va to'g'ri javob alohida **jadval (table)** ichida:

```
Answer  B — izoh...
```

### 2. PDF (explanation edition) — `parse_explanation_pdf()`

```
Question 1
Question: What is the question text?
A) Variant A
B) Variant B
C) Variant C
D) Variant D
Correct Answer: B) Variant B
```

> 🔎 **Bir nechta to'g'ri javobli savollar** (masalan `Correct Answer: C) ... and D) ...`) avtomatik **chiqarib tashlanadi**, chunki Telegram quiz poll faqat bitta to'g'ri javobni qo'llaydi.

### Validatsiya

Savol bazaga tushishi uchun kamida `question`, `option_a`, `option_b` va `correct_answer` to'ldirilgan bo'lishi shart (`_is_complete()`).

---

## 🗄 Ma'lumotlar bazasi

SQLite fayli: `questions.db` (loyiha papkasida avtomatik yaratiladi).

### `questions` jadvali

| Ustun            | Tip     | Tavsifi                          |
| ---------------- | ------- | -------------------------------- |
| `id`             | INTEGER | Primary key (auto-increment)     |
| `question`       | TEXT    | Savol matni                      |
| `option_a..d`    | TEXT    | Variantlar A, B, C, D            |
| `correct_answer` | TEXT    | To'g'ri variant harfi (`A`–`D`)  |
| `source_file`    | TEXT    | Qaysi fayldan kelgani            |

### `user_stats` jadvali

| Ustun            | Tip     | Tavsifi                       |
| ---------------- | ------- | ----------------------------- |
| `user_id`        | INTEGER | Telegram user ID (primary key) |
| `total_sessions` | INTEGER | Tugatilgan testlar soni         |
| `total_correct`  | INTEGER | To'g'ri javoblar soni           |
| `total_answered` | INTEGER | Javob berilgan savollar soni    |

---

## ☁️ Deploy (Railway / Heroku)

Loyihada deploy uchun tayyor fayllar bor:

- **`Procfile`** → `worker: python bot.py` (web emas, worker process)
- **`runtime.txt`** → `python-3.11.9`
- **`mise.toml`** → mise/asdf tool sozlamalari

Bot **polling** rejimida ishlaydi (webhook emas), shuning uchun ochiq port talab qilinmaydi — `worker` dyno/service yetarli.

### Railway misoli

1. Repo'ni Railway'ga ulang.
2. Environment Variables'ga `BOT_TOKEN` va `ADMIN_ID` ni qo'shing.
3. Start command avtomatik `Procfile` dan olinadi.

> ⚠️ **Diqqat:** `questions.db` lokal fayl. Ko'pchilik platformalarda fayl tizimi **vaqtinchalik (ephemeral)** — deploy/restart'da o'chib ketishi mumkin. Savollar saqlanib qolishi uchun persistent volume ulang yoki `/load` ni har deploydan keyin qayta bajaring.

---

## 📁 Loyiha tuzilishi

```
microsoft-mock/
├── bot.py              # Telegram bot — handlerlar, sessiyalar, quiz poll
├── database.py         # SQLite: savollar + statistika
├── parser.py           # DOCX/PDF → savollar ro'yxati
├── questions.db        # SQLite bazasi (avtomatik yaratiladi)
├── docs/               # Yuklanadigan DOCX/PDF fayllar (avtomatik yaratiladi)
├── requirements.txt    # Python kutubxonalar
├── runtime.txt         # Python versiyasi (deploy uchun)
├── Procfile            # Process turi (deploy uchun)
├── mise.toml           # mise/asdf sozlamalari
├── .env                # BOT_TOKEN, ADMIN_ID (git'ga tushmaydi)
└── .gitignore
```

### Asosiy konstantalar (`bot.py`)

| Konstanta    | Qiymati | Tavsifi                          |
| ------------ | ------- | -------------------------------- |
| `CHUNK_SIZE` | `50`    | Bir qismdagi savollar soni       |

Savol matni `299`, variant matni `99` belgida kesiladi (Telegram poll cheklovi).

---

## 🛠 Tez-tez uchraydigan muammolar

| Muammo                                              | Yechim                                                                                 |
| --------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'docx'`       | `pip install python-docx` (DOCX yuklash uchun)                                          |
| `ModuleNotFoundError: No module named 'pdfplumber'` | `pip install pdfplumber` (PDF yuklash uchun)                                            |
| Bot ishga tushmaydi, `BOT_TOKEN` xatosi             | `.env` faylda `BOT_TOKEN` to'g'ri yozilganini tekshiring                                |
| `/load` "Sizda ruxsat yo'q" deydi                   | `.env` dagi `ADMIN_ID` sizning Telegram ID'ingiz bilan mos kelishini tekshiring         |
| `docs/ papkasi bo'sh`                               | DOCX/PDF fayllarni `docs/` ichiga joylab, qayta `/load` bering                          |
| To'g'ri/noto'g'ri sanalmayapti                      | `allowed_updates` da `poll_answer` borligini va poll'lar `is_anonymous=False` ekanini tekshiring |
| Savollar ko'rinmayapti                              | Avval admin `/load` bilan savollarni yuklashi kerak; `/count` bilan tekshiring          |

---

## 📝 Litsenziya

Ichki/shaxsiy foydalanish uchun. Litsenziya ko'rsatilmagan.
