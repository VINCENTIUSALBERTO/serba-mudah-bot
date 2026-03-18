# 🤖 Serba Mudah Bot

Bot Telegram untuk jualan akun premium, dibangun dengan **python-telegram-bot v20+**, **Supabase**, dan **python-dotenv**.

---

## 📦 Struktur Proyek

```
serba-mudah-bot/
├── main.py               # Entry point — jalankan bot di sini
├── requirements.txt      # Daftar library Python
├── .env.example          # Contoh file environment variable
├── .gitignore
├── README.md
└── bot/
    ├── config.py         # Memuat env vars dari .env
    ├── database.py       # Supabase client & helper query
    ├── handlers/
    │   ├── start.py      # /start command & menu utama
    │   ├── catalog.py    # Browse produk
    │   ├── order.py      # Alur pemesanan
    │   └── admin.py      # Perintah khusus admin
    └── utils/
        └── keyboards.py  # InlineKeyboard builders
```

---

## 🚀 Cara Instalasi

### 1. Clone repositori & buat virtual environment

```bash
git clone https://github.com/VINCENTIUSALBERTO/serba-mudah-bot.git
cd serba-mudah-bot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 2. Install library

```bash
pip install -r requirements.txt
```

Library yang diinstall:

| Library | Fungsi |
|---|---|
| `python-telegram-bot==20.7` | Framework bot Telegram (async) |
| `supabase==2.3.4` | Client Supabase (database & auth) |
| `python-dotenv==1.0.1` | Memuat variabel dari file `.env` |
| `httpx==0.26.0` | HTTP client (dependensi supabase-py) |

### 3. Buat file `.env`

Salin `.env.example` menjadi `.env` lalu isi nilainya:

```bash
cp .env.example .env
```

```dotenv
# Telegram Bot Token (dari @BotFather)
BOT_TOKEN=your_telegram_bot_token_here

# Supabase project URL dan API key
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_supabase_anon_or_service_role_key_here

# Telegram user ID admin (pisahkan dengan koma jika lebih dari satu)
ADMIN_IDS=123456789

# (Opsional) ID channel/group untuk notifikasi pesanan baru
PAYMENT_CHANNEL_ID=-100123456789
```

---

## 🗄️ Skema Database Supabase

Buat dua tabel berikut di Supabase SQL editor:

```sql
-- Tabel produk
create table products (
  id          bigint generated always as identity primary key,
  name        text        not null,
  description text,
  price       numeric     not null,
  is_active   boolean     not null default true,
  created_at  timestamptz not null default now()
);

-- Tabel pesanan
create table orders (
  id          bigint generated always as identity primary key,
  user_id     bigint      not null,
  username    text,
  product_id  bigint      references products(id),
  status      text        not null default 'pending',
  created_at  timestamptz not null default now()
);

-- Tabel users (saldo)
create table users (
  id          bigint primary key,        -- Telegram user ID
  username    text,
  balance     numeric not null default 0,
  created_at  timestamptz not null default now()
);

-- Tabel top-up saldo
create table topups (
  id               bigint generated always as identity primary key,
  user_id          bigint not null references users(id),
  amount           numeric not null,
  status           text not null default 'pending', -- pending/approved/rejected
  proof_message_id bigint,
  created_at       timestamptz not null default now()
);
```

---

## ▶️ Menjalankan Bot

```bash
python main.py
```

---

## 🛠️ Fitur

| Fitur | Keterangan |
|---|---|
| `/start` | Tampilkan menu utama |
| Katalog produk | Daftar produk aktif dari Supabase |
| Detail produk | Harga & deskripsi |
| Pesan produk | Buat pesanan & kirim instruksi bayar |
| Pesanan saya | Riwayat pembelian pengguna |
| Notifikasi admin | Kirim detail pesanan ke channel admin |
| Setujui/Tolak pesanan | Tombol aksi khusus admin |
| `/stats` (admin) | Statistik bot |
| `/balance` / `/saldo` | Cek saldo pengguna |
| `/topup <nominal>` | Ajukan top-up saldo (manual transfer, admin approve) |
| `/addsaldo <user_id> <nominal>` (admin) | Tambah saldo pengguna secara langsung |
| `/add_product` (admin) | Tambah produk baru |
| `/edit_product` (admin) | Ubah harga/deskripsi produk |
| `/delete_product` (admin) | Nonaktifkan/hapus produk |
| `/list_products` (admin) | Lihat semua produk (termasuk nonaktif) |
