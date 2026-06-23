# Final Project Teknologi Komputasi Awan 2026
## Kelompok C02 — Order Processing Service

### Anggota Kelompok

| Nama | NRP |
|------|-----|
| Oryza Qiara Ramadhani | 5027241084 |
| Az Zahrra Tasya Adelia | 5027241087 |
| Naila Raniyah Hanan | 5027241078 |
| Nadia Kirana Afifah Prahandita | 5027241005 |
| Muhammad Huda Rabbani | 5027241098 |
| Kaisar Hanif Pratama | 5027241029 |
| Gemilang Ananda Lingua | 5027241072 |
| Angga Firmansyah | 5027241062 |

---

## 1. Introduction

Proyek ini merupakan implementasi **Order Processing Service** — layanan backend inti untuk platform e-commerce yang menangani pembuatan pesanan, pengecekan status, dan riwayat transaksi. Layanan ini di-deploy di atas infrastruktur cloud **Microsoft Azure** dengan arsitektur yang dirancang untuk menangani lonjakan traffic tinggi seperti flash sale dan promo.

Tantangan utama yang diselesaikan:
- Deploy REST API berbasis Flask yang dapat melayani ribuan request per detik
- Konfigurasi Load Balancer untuk distribusi traffic ke multiple backend VM
- Optimasi performa dengan Gunicorn multi-worker dan Nginx sebagai reverse proxy
- Pengujian kapasitas sistem melalui load testing dengan Locust

---

## 2. Arsitektur Cloud

### Diagram Arsitektur

> **[PLACEHOLDER — Masukkan gambar diagram draw.io di sini]**
> `![Arsitektur Cloud](result/architecture.png)`

Arsitektur yang diimplementasikan menggunakan 3 VM di Microsoft Azure:

```
Internet (Client Browser / Locust)
                │
                ▼
    ┌─────────────────────────┐
    │   vm-lb-fe              │
    │   Public IP: 70.153.148.59  │
    │   Private IP: 10.0.0.4  │
    │   Nginx Load Balancer   │
    │   + Frontend (HTML/CSS) │
    └───────────┬─────────────┘
                │ Round-Robin
        ┌───────┴────────┐
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│   vm-be1     │  │   vm-be2     │
│ 10.0.0.5     │  │ 10.0.0.6     │
│ Flask API    │  │ Flask API    │
│ Gunicorn     │  │ Gunicorn     │
│ Nginx        │  │ Nginx        │
│ MongoDB ←────┘  │              │
└──────────────┘  └──────────────┘
     (Port 27017, internal only)
```

**Catatan Arsitektur:**
- MongoDB di-install di vm-be1 (bukan VM terpisah) sebagai trade-off budget
- vm-be2 terhubung ke MongoDB di vm-be1 via private IP (10.0.0.5:27017)
- Frontend di-serve langsung dari vm-lb-fe oleh Nginx
- Semua API request di-route via `/api/` prefix oleh Nginx LB ke backend

### Spesifikasi VM & Estimasi Biaya

| VM | Fungsi | Size | vCPU | RAM | OS | Harga/Bulan |
|----|--------|------|------|-----|----|-------------|
| vm-lb-fe | Nginx LB + Frontend | [ISI SIZE] | [ISI] | [ISI] GB | Ubuntu 22.04 | $[ISI] |
| vm-be1 | Flask + Gunicorn + MongoDB | [ISI SIZE] | [ISI] | [ISI] GB | Ubuntu 22.04 | $[ISI] |
| vm-be2 | Flask + Gunicorn | [ISI SIZE] | [ISI] | [ISI] GB | Ubuntu 22.04 | $[ISI] |
| **Total** | | | | | | **$[ISI]/bulan** |

> Budget maksimal: $75/bulan (~Rp1.3 juta). Total biaya di atas dalam batas budget.

### Justifikasi Pemilihan Konfigurasi

**Kenapa 2 VM Backend + 1 VM LB/FE:**
Pemisahan Load Balancer dari backend memungkinkan distribusi traffic yang efisien tanpa menambah beban ke server aplikasi. Dengan 2 VM backend, sistem tetap available jika salah satu VM mengalami gangguan (basic redundancy).

**Kenapa MongoDB di vm-be1 (bukan VM terpisah):**
Pertimbangan budget — memisahkan MongoDB ke VM ketiga akan menambah biaya ~$15-20/bulan. Dengan menempatkan MongoDB di vm-be1 dan mengakses dari vm-be2 via private IP, latensi tetap rendah (<1ms) karena berada di virtual network yang sama.

**Kenapa Nginx sebagai LB (bukan Azure LB):**
Nginx memberikan fleksibilitas konfigurasi routing yang lebih detail (memisahkan traffic API vs static file) dengan zero additional cost, sesuai constraint budget $75/bulan.

---

## 3. Implementasi

### 3.1 Setup VM di Azure

Ketiga VM dibuat di Microsoft Azure dengan konfigurasi:
- **Region:** [ISI REGION]
- **OS:** Ubuntu 22.04 LTS
- **Authentication:** SSH key pair
- **Virtual Network:** Shared VNet (10.0.0.0/24)

Kredensial SSH:
```
User: azureuser
Password: TkaFP2026!Azure
```

IP Summary:
```
vm-lb-fe : Public 70.153.148.59  | Private 10.0.0.4
vm-be1   : Public 70.153.149.199 | Private 10.0.0.5
vm-be2   : Public 48.193.47.130  | Private 10.0.0.6
```

### 3.2 Konfigurasi Nginx Load Balancer (vm-lb-fe)

SSH ke vm-lb-fe:
```bash
ssh azureuser@70.153.148.59
```

Install Nginx:
```bash
sudo apt update && sudo apt install -y nginx
```

Konfigurasi Nginx sebagai Load Balancer + serve frontend:
```bash
sudo nano /etc/nginx/sites-available/lb
```

```nginx
upstream backend {
    server 10.0.0.5:80;
    server 10.0.0.6:80;
}

server {
    listen 80;
    server_name _;

    # Route API ke backend pool
    location /api/ {
        rewrite ^/api(/.*)$ $1 break;
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /order {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /orders {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://backend;
        proxy_set_header Host $host;
    }

    # Serve frontend dari lokal
    location / {
        root /var/www/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/lb /etc/nginx/sites-enabled/lb
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl enable nginx && sudo systemctl start nginx
```

Deploy frontend:
```bash
sudo mkdir -p /var/www/html
sudo cp ~/index.html ~/styles.css /var/www/html/
sudo chmod 644 /var/www/html/*
sudo chown -R www-data:www-data /var/www/html/
sudo systemctl reload nginx
```

### 3.3 Deploy Backend Flask + Gunicorn (vm-be1 & vm-be2)

SSH ke vm-be1:
```bash
ssh azureuser@70.153.149.199
```

Setup Python virtual environment & install dependencies:
```bash
python3 -m venv ~/venv
~/venv/bin/pip install flask pymongo gunicorn
```

Upload app.py:
```bash
# Dari laptop lokal:
scp Resources/BE/app.py azureuser@70.153.149.199:~/app.py
```

Setup systemd service untuk Gunicorn:
```bash
sudo nano /etc/systemd/system/order-api.service
```

```ini
[Unit]
Description=Gunicorn instance to serve Order API
After=network.target

[Service]
User=azureuser
WorkingDirectory=/home/azureuser
ExecStart=/home/azureuser/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable order-api
sudo systemctl start order-api
```

Konfigurasi Nginx sebagai reverse proxy di vm-be1:
```bash
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/order-api
```

```nginx
server {
    listen 80;
    server_name _;

    location /order {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /orders {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
    }

    location / {
        root /var/www/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/order-api /etc/nginx/sites-enabled/order-api
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl enable nginx && sudo systemctl start nginx
```

Ulangi langkah yang sama untuk vm-be2, dengan perbedaan `MONGO_HOST`:
```bash
# Di vm-be2, app.py menggunakan MongoDB dari vm-be1
sed -i 's/MONGO_HOST", "127.0.0.1"/MONGO_HOST", "10.0.0.5"/' ~/app.py
```

### 3.4 Instalasi & Konfigurasi MongoDB (vm-be1)

```bash
# Install MongoDB 7.x
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt update && sudo apt install -y mongodb-org
sudo systemctl enable mongod && sudo systemctl start mongod
```

Verifikasi koneksi:
```bash
mongosh --eval "db.adminCommand('ping')"
```

---

## 4. Hasil Pengujian Endpoint

Pengujian dilakukan menggunakan **Postman** dengan target `http://70.153.148.59` (Load Balancer public IP).

### 4.1 POST /order — Create Order (201 Created)

Request:
```json
{
  "product": "Sepatu Running",
  "quantity": 2,
  "price": 150000
}
```

> **[PLACEHOLDER — Screenshot Postman POST 201]**
> `![POST /order 201](result/postman_post_201.png)`

Response (201 Created):
```json
{
  "order_id": "0e1f0533-5b81-4221-9231-101969c31e4e",
  "product": "Sepatu Running",
  "quantity": 2,
  "price": 150000.0,
  "total": 300000.0,
  "status": "pending",
  "created_at": "2026-06-20T04:06:43Z"
}
```

### 4.2 GET /orders — Get All Orders (200 OK)

> **[PLACEHOLDER — Screenshot Postman GET /orders 200]**
> `![GET /orders 200](result/postman_get_orders_200.png)`

### 4.3 GET /order/\<id\> — Get Order by ID (200 OK)

> **[PLACEHOLDER — Screenshot Postman GET /order/id 200]**
> `![GET /order/id 200](result/postman_get_order_id_200.png)`

### 4.4 GET /order/\<invalid-id\> — Order Not Found (404)

> **[PLACEHOLDER — Screenshot Postman GET 404]**
> `![GET /order/invalid 404](result/postman_get_404.png)`

Response (404 Not Found):
```json
{
  "error": "Order not found"
}
```

### 4.5 PUT /order/\<id\> — Update Status (200 OK)

Request:
```json
{
  "status": "completed"
}
```

> **[PLACEHOLDER — Screenshot Postman PUT 200]**
> `![PUT /order/id 200](result/postman_put_200.png)`

Response (200 OK):
```json
{
  "order_id": "0e1f0533-5b81-4221-9231-101969c31e4e",
  "status": "completed"
}
```

### 4.6 Tampilan Frontend

> **[PLACEHOLDER — Screenshot frontend di browser]**
> `![Frontend](result/frontend.png)`

Frontend dapat diakses di `http://70.153.148.59` dan berhasil terhubung ke API backend melalui endpoint `/api/`.

---

## 5. Hasil Load Testing

Load testing dilakukan menggunakan **Locust 2.44.4** dari laptop lokal (bukan dari server) dengan target `http://70.153.148.59`.

### 5.1 Skenario 1 — Maksimum RPS (0% Failure)

**Parameter:** User dinaikkan bertahap, durasi 60 detik per percobaan

> **[PLACEHOLDER — Screenshot Charts S1]**
> `![Charts S1](result/s1_charts.png)`

> **[PLACEHOLDER — Screenshot Statistics S1]**
> `![Statistics S1](result/s1_statistics.png)`

> **[PLACEHOLDER — Screenshot htop S1]**
> `![htop S1](result/s1_htop.png)`

**Hasil:** RPS Tertinggi = **[ISI]** dengan Failure Rate **0%**

### 5.2 Skenario 2 — Peak Concurrency Spawn Rate 50

> `![Charts S2](result/s2_charts.png)`
> `![Statistics S2](result/s2_statistics.png)`
> `![htop S2](result/s2_htop.png)`

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.3 Skenario 3 — Peak Concurrency Spawn Rate 100

> `![Charts S3](result/s3_charts.png)`
> `![Statistics S3](result/s3_statistics.png)`
> `![htop S3](result/s3_htop.png)`

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.4 Skenario 4 — Peak Concurrency Spawn Rate 200

> `![Charts S4](result/s4_charts.png)`
> `![Statistics S4](result/s4_statistics.png)`
> `![htop S4](result/s4_htop.png)`

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.5 Skenario 5 — Peak Concurrency Spawn Rate 500

> `![Charts S5](result/s5_charts.png)`
> `![Statistics S5](result/s5_statistics.png)`
> `![htop S5](result/s5_htop.png)`

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.6 Tabel Ringkasan Hasil

| Skenario | Spawn Rate | Max Users (0% fail) | RPS Tertinggi | Avg Response Time | Failure Rate |
|----------|------------|---------------------|---------------|-------------------|--------------|
| 1 — Maks RPS | Bertahap | [ISI] | [ISI] RPS | [ISI] ms | 0% |
| 2 — SR 50 | 50 | [ISI] | [ISI] RPS | [ISI] ms | 0% |
| 3 — SR 100 | 100 | [ISI] | [ISI] RPS | [ISI] ms | 0% |
| 4 — SR 200 | 200 | [ISI] | [ISI] RPS | [ISI] ms | 0% |
| 5 — SR 500 | 500 | [ISI] | [ISI] RPS | [ISI] ms | 0% |

### 5.7 Analisis Bottleneck

Berdasarkan hasil load testing dan monitoring resource (htop):

**Bottleneck utama yang ditemukan:**

1. **GET /orders — Response Time Tinggi**
   Endpoint `GET /orders` mengembalikan seluruh koleksi data tanpa pagination, sehingga response time meningkat signifikan seiring bertambahnya data di MongoDB (avg 2849ms pada 50 user). Ini menjadi bottleneck utama sebelum CPU.

2. **Gunicorn Worker Terbatas**
   Dengan hanya 3 Gunicorn workers per VM, sistem mulai mengalami 502 Bad Gateway saat concurrent user mencapai >400 karena worker queue penuh.

3. **MongoDB di VM yang Sama dengan Backend (BE1)**
   MongoDB berbagi resource CPU dan memory dengan Flask/Gunicorn di vm-be1, sehingga under heavy load keduanya berkompetisi untuk resource yang sama.

4. **CPU Usage Rendah**
   CPU BE1 hanya mencapai ~13% saat 200 user — membuktikan bottleneck ada di I/O (MongoDB query) dan connection handling, bukan CPU compute.

---

## 6. Kesimpulan dan Saran

### Kesimpulan

Sistem Order Processing Service berhasil di-deploy di atas infrastruktur Microsoft Azure dengan arsitektur 3 VM (1 LB/FE + 2 Backend) dan mampu melayani hingga **[ISI] RPS** dengan 0% failure rate.

Dari hasil load testing:
- Sistem stabil hingga **[ISI] concurrent user** dengan spawn rate bertahap
- Bottleneck utama bukan di CPU melainkan di response time `GET /orders` yang tidak ter-paginate
- Error 502 muncul saat >400 concurrent user akibat Gunicorn worker exhaustion

### Saran untuk Deployment Produksi

1. **Tambah Gunicorn Workers**
   Ubah dari 3 ke `(2 × jumlah_vCPU) + 1` workers untuk memaksimalkan throughput per VM.

2. **Implementasi Pagination pada GET /orders**
   Tambahkan parameter `?limit=50&skip=0` agar tidak mengembalikan seluruh koleksi sekaligus.

3. **Pisahkan MongoDB ke VM Terpisah**
   Menempatkan MongoDB di VM tersendiri menghilangkan resource contention dengan proses Flask/Gunicorn.

4. **Tambah Index MongoDB**
   ```javascript
   db.orders.createIndex({ created_at: -1 })
   db.orders.createIndex({ order_id: 1 }, { unique: true })
   ```

5. **Scale Out Backend**
   Tambah VM Backend ke-3 dan ke-4 ke pool Nginx LB untuk meningkatkan throughput secara linear.

6. **Gunakan Azure Cache for Redis**
   Cache hasil `GET /orders` dengan TTL pendek (1-5 detik) untuk mengurangi beban MongoDB saat flash sale.
