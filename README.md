# Healthify

Tugas Besar II3160 Teknologi Sistem Terintegrasi x II3140 Pengembangan Aplikasi Web dan Mobile
Kelompok unayaha (K02)

| Nama | NIM | Peran |
|---|---|---|
| Endda Tsa Azzahra Syaifur | 18224094 | Mobile Developer |
| Gifta Mooira Prasharnissa | 18224106 | Backend dan Bisnis |

Healthify adalah layanan untuk mencatat obat rutin dan memperkirakan risiko kesehatan musiman dari data cuaca. Layanan ini mengambil prakiraan kelembaban dan curah hujan dari Open-Meteo, lalu menghitung skor risiko untuk 7 hari ke depan. Skor itu dibandingkan dengan sisa stok obat pengguna, supaya pengguna tahu apakah stoknya cukup untuk melewati periode yang rawan.

Catatan: di laporan Tugas 1 nama layanannya masih Healther, lalu kami ganti jadi Healthify. Healthify bukan alat diagnosis, dan semua data yang dipakai adalah data uji.

- Base URL: `https://healthify.stei.site/api`
- Dokumentasi (Swagger): `https://healthify.stei.site/api/docs`
- OpenAPI: `https://healthify.stei.site/api/openapi.json`


## Arsitektur

Semua service jalan di STB pakai Docker Compose. Akses dari luar lewat Cloudflare Tunnel, jadi tidak ada port yang dibuka ke internet.

```
Aplikasi mobile / kelompok lain
            |
   https://healthify.stei.site
            |
   [tunnel]  cloudflared
            |
   [gateway] nginx  -> rate limit 10 req/detik per IP
            |
   [core-service] FastAPI (Python)  -> SQLite (volume docker)
            |
   Open-Meteo (prakiraan cuaca)
```

| Kontainer | Isi | Batas resource |
|---|---|---|
| core-service | FastAPI, logika domain, auth, database SQLite | 256 MB, 0.5 CPU |
| gateway | nginx 1.28, pintu masuk `/api` dan rate limit | 64 MB, 0.25 CPU |
| tunnel | cloudflared, untuk akses publik | 128 MB, 0.25 CPU |

Ketiganya pakai `restart: unless-stopped`, jadi kalau STB mati lalu nyala lagi, service ikut jalan lagi.

Pembagian kode di `core-service/app` mengikuti bounded context dari Tugas 1:

- `domain.py`: logika inti (skor risiko dan kesiapan stok). Isinya fungsi biasa tanpa database, jadi gampang dites.
- `weather.py`: penerjemah data Open-Meteo ke istilah domain kami ("hari lembab", "hari hujan"). Kalau format Open-Meteo berubah, cukup file ini yang diubah. Hasilnya di-cache 1 jam.
- `security.py`: hash password, JWT, dan pengecekan API key.
- `db.py`: tabel `users` dan `medicines`.
- `main.py`: daftar endpoint.


## Autentikasi

Ada dua cara, tergantung siapa yang memanggil.

| Pemanggil | Cara | Header |
|---|---|---|
| Pengguna aplikasi | login dulu, dapat token JWT (berlaku 24 jam) | `Authorization: Bearer <token>` |
| Kelompok lain | API key dari kami | `X-API-Key: <key>` |

### Cara dapat API key

Hubungi kami (kontak di bawah) dan sebutkan nama kelompok kalian. Satu kelompok dapat satu key. Key dipakai untuk endpoint `/api/public/risk`.

Kalau mau coba endpoint yang butuh login, pakai akun uji ini:

- email: `demo@healthify.id`
- password: `demo12345`


## Daftar Endpoint

| Method | Path | Auth | Fungsi |
|---|---|---|---|
| GET | `/api/health` | - | cek service hidup |
| POST | `/api/auth/register` | - | daftar akun |
| POST | `/api/auth/login` | - | login, dapat token |
| GET | `/api/profile` | JWT | lihat profil |
| PUT | `/api/profile` | JWT | isi lokasi dan kerentanan |
| GET | `/api/medicines` | JWT | daftar obat |
| POST | `/api/medicines` | JWT | tambah obat |
| DELETE | `/api/medicines/{id}` | JWT | hapus obat |
| GET | `/api/readiness` | JWT | skor risiko + saran stok (fitur utama) |
| GET | `/api/public/risk?lat=&lon=` | API key | skor risiko per lokasi, untuk kelompok lain |

Kode status yang mungkin keluar:

| Kode | Artinya |
|---|---|
| 200 / 201 | berhasil |
| 400 | profil belum diisi (lokasi kosong) |
| 401 | token atau API key salah / tidak ada |
| 404 | data tidak ditemukan |
| 409 | email sudah terdaftar |
| 422 | format input salah |
| 429 | terlalu banyak request, tunggu sebentar |
| 503 | Open-Meteo sedang tidak bisa dihubungi |


## Contoh Request

Login:

```bash
curl -X POST https://healthify.stei.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "demo@healthify.id", "password": "demo12345"}'
```

```json
{"access_token": "eyJhbGciOi...", "token_type": "bearer"}
```

Isi profil dan tambah obat (token dari login di atas):

```bash
curl -X PUT https://healthify.stei.site/api/profile \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -6.89, "longitude": 107.61, "vulnerabilities": ["asma"]}'

curl -X POST https://healthify.stei.site/api/medicines \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Salbutamol", "dose_per_intake": 1, "intakes_per_day": 3, "stock_units": 8}'
```

Cek kesiapan:

```bash
curl https://healthify.stei.site/api/readiness \
  -H "Authorization: Bearer <token>"
```

```json
{
  "risk_score": 89,
  "risk_level": "tinggi",
  "humid_days": 6,
  "rainy_days": 4,
  "stock_days_left": 2.7,
  "advice": "Risiko tinggi diperkirakan dalam 7 hari ke depan, sedangkan stok obat hanya cukup sekitar 3 hari. Pertimbangkan menambah stok sebelum periode rawan.",
  "disclaimer": "Bukan diagnosis; bukan pengganti saran tenaga medis."
}
```

Endpoint untuk kelompok lain:

```bash
curl "https://healthify.stei.site/api/public/risk?lat=-6.89&lon=107.61" \
  -H "X-API-Key: <key-kelompok-kalian>"
```

```json
{
  "lat": -6.89,
  "lon": 107.61,
  "risk_score": 74,
  "risk_level": "tinggi",
  "humid_days": 6,
  "rainy_days": 4,
  "horizon_days": 7
}
```

Contoh angka di atas diambil dari hasil tes kami untuk Bandung tanggal 22 November 2026, jadi hasilnya akan beda tergantung cuaca saat dipanggil.


## Cara Skor Dihitung

1. Ambil prakiraan 7 hari dari Open-Meteo.
2. Satu hari dihitung "lembab" kalau kelembaban rata-ratanya 80% ke atas, dan "hujan" kalau curah hujannya 10 mm ke atas.
3. Skor = 100 x (0,6 x proporsi hari lembab + 0,4 x proporsi hari hujan).
4. Kalau pengguna punya kerentanan (misalnya asma), skor dikali 1,2. Skor maksimal 100.
5. Level: 0-33 rendah, 34-66 sedang, 67-100 tinggi.
6. Sisa stok = stok / (dosis x frekuensi per hari), diambil dari obat yang paling cepat habis. Kalau risikonya sedang atau tinggi dan stok kurang dari 7 hari, pengguna dapat saran untuk menambah stok.

Endpoint `/api/public/risk` memakai rumus yang sama tanpa pengali kerentanan, karena tidak ada data pengguna di sana.


## Menjalankan Sendiri

Butuh Docker dan Docker Compose.

```bash
git clone https://github.com/giftamooi/healthify_unayaha.git
cd healthify_unayaha
cp .env.example .env
```

Isi `.env`:

- `JWT_SECRET`: string acak panjang, misalnya dari `openssl rand -hex 32`
- `API_KEYS`: API key untuk kelompok lain, dipisah koma kalau lebih dari satu
- `DB_PATH`: biarkan `/data/healthify.db`
- `TUNNEL_TOKEN` dan `COMPOSE_PROFILES=tunnel`: hanya diisi di STB

Lalu jalankan:

```bash
docker compose up -d --build
docker compose ps
```

Buka `http://localhost:8080/api/docs` untuk mencoba. Unit test bisa dijalankan dari folder `core-service` dengan `pip install -r requirements.txt` lalu `python -m pytest`.

Kalau `.env` diubah, kontainer perlu dibuat ulang supaya perubahannya terbaca:

```bash
docker compose up -d --force-recreate
```
