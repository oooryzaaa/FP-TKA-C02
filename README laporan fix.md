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

Sebagai Cloud Engineer, tantangan yang diselesaikan meliputi:
- Deploy REST API berbasis **Python Flask** yang dapat melayani ribuan request per detik
- Konfigurasi **Nginx Load Balancer** untuk distribusi traffic ke multiple backend VM
- Optimasi performa dengan **Gunicorn multi-worker** dan Nginx sebagai reverse proxy
- **MongoDB** sebagai database dengan index optimasi untuk query cepat
- Pengujian kapasitas sistem melalui load testing dengan **Locust** 5 skenario

---

## 2. Arsitektur Cloud

### Diagram Arsitektur

![Arsitektur Cloud](result/architecture.png)

Arsitektur yang diimplementasikan menggunakan **3 VM** di Microsoft Azure dalam satu Virtual Network:

```
Internet (Client Browser / Locust)
                │
                ▼
    ┌───────────────────────────┐
    │        vm-lb-fe           │
    │  Public IP: 70.153.148.59 │
    │  Private IP: 10.0.0.4     │
    │  Nginx Load Balancer      │
    │  + Frontend (HTML/CSS)    │
    └────────────┬──────────────┘
                 │ Round-Robin (port 80)
         ┌───────┴────────┐
         ▼                ▼
┌─────────────────┐  ┌─────────────────┐
│    vm-be1       │  │    vm-be2       │
│  10.0.0.5       │  │  10.0.0.6       │
│  Flask (port 5000) │  │  Flask (port 5000) │
│  Gunicorn       │  │  Gunicorn       │
│  Nginx (port 80)│  │  Nginx (port 80)│
│  MongoDB ◄──────┼──┘  (port 27017)  │
│  (port 27017)   │                   │
└─────────────────┘  └─────────────────┘
```

**Catatan Desain:**
- MongoDB di-install di **vm-be1** (bukan VM terpisah) sebagai pertimbangan efisiensi budget
- vm-be2 mengakses MongoDB di vm-be1 via **private IP 10.0.0.5:27017** (internal network, latensi <1ms)
- Frontend di-serve langsung dari **vm-lb-fe** oleh Nginx (tidak di-forward ke backend)
- Semua API request di-proxy oleh Nginx LB ke upstream backend pool (BE1 + BE2)

### Spesifikasi VM & Estimasi Biaya

| Komponen | Instance | vCPU | RAM | Storage | Harga/Bulan |
|----------|----------|------|-----|---------|-------------|
| VM Backend | B2s | 2 | 4 GB | 30 GB | ~$35 |
| VM MongoDB | B1s | 1 | 1 GB | 30 GB | ~$15 |
| Azure Load Balancer | Basic | — | — | — | ~$18 |
| **Total** | | | | | **~$68/bulan ✅** |

> Total di bawah budget $75 (~Rp1.3 juta) — sisa ~$7 untuk buffer

### Justifikasi Pemilihan Konfigurasi

- Kenapa B2s untuk backend: 2 vCPU dedicated cukup untuk handle Gunicorn multi-worker
- Kenapa B1s untuk MongoDB: DB tidak kena traffic langsung, burstable CPU cukup
- Kenapa Load Balancer Basic: budget terbatas, fitur Basic sudah cukup untuk FP ini
- Trade-off: B1s burstable CPU bisa throttle jika terus-menerus dipakai intensif

## 3. Implementasi

### 3.1 Informasi VM

| VM | Public IP | Private IP |
|----|-----------|------------|
| vm-lb-fe | 70.153.148.59 | 10.0.0.4 |
| vm-be1 | 70.153.149.199 | 10.0.0.5 |
| vm-be2 | 48.193.47.130 | 10.0.0.6 |

SSH credentials:
```
User     : azureuser
Password : TkaFP2026!Azure
```

### 3.2 Setup MongoDB (vm-be1)

SSH ke vm-be1:
```bash
ssh azureuser@70.153.149.199
```

Install MongoDB 7.x:
```bash
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt update && sudo apt install -y mongodb-org
```

Konfigurasi `bindIp` agar MongoDB bisa diakses dari vm-be2:
```bash
sudo nano /etc/mongod.conf
# Ubah baris bindIp:
# bindIp: 127.0.0.1 → bindIp: 127.0.0.1,10.0.0.5
```

Start & enable MongoDB:
```bash
sudo systemctl enable mongod && sudo systemctl start mongod
sudo systemctl status mongod
```

Buat index untuk optimasi query:
```bash
mongosh orders_db --eval "
db.orders.insertOne({temp: true});
db.orders.createIndex({ created_at: -1 });
db.orders.createIndex({ order_id: 1 }, { unique: true });
db.orders.deleteOne({temp: true});
printjson(db.orders.getIndexes());
"
```

Output konfirmasi index:
```json
[
  { "key": { "_id": 1 }, "name": "_id_" },
  { "key": { "created_at": -1 }, "name": "created_at_-1" },
  { "key": { "order_id": 1 }, "name": "order_id_1", "unique": true }
]
```

### 3.3 Deploy Flask + Gunicorn (vm-be1 & vm-be2)

Langkah berikut dilakukan di **kedua VM** (vm-be1 dan vm-be2).

SSH ke vm-be1:
```bash
ssh azureuser@70.153.149.199
```

Setup Python virtual environment & install dependencies:
```bash
python3 -m venv ~/venv
~/venv/bin/pip install flask pymongo gunicorn
```

Deploy `app.py`:
```bash
# Upload dari laptop lokal ke vm-be1
scp Resources/BE/app.py azureuser@70.153.149.199:~/app.py

# Copy dari vm-be1 ke vm-be2 via internal network
scp azureuser@10.0.0.5:~/app.py ~/app.py
```

Konfigurasi `MONGO_HOST` di masing-masing VM:
```bash
# Di vm-be1: MongoDB lokal
grep MONGO_HOST ~/app.py
# MONGO_HOST = os.environ.get("MONGO_HOST", "127.0.0.1")

# Di vm-be2: MongoDB di vm-be1 via private IP
sed -i 's/MONGO_HOST", "127.0.0.1"/MONGO_HOST", "10.0.0.5"/' ~/app.py
grep MONGO_HOST ~/app.py
# MONGO_HOST = os.environ.get("MONGO_HOST", "10.0.0.5")
```

Setup systemd service untuk Gunicorn (kedua VM):
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

# Verifikasi
sudo systemctl status order-api
curl http://localhost:5000/orders
```

### 3.4 Setup Nginx Reverse Proxy (vm-be1 & vm-be2)

Install Nginx:
```bash
sudo apt update && sudo apt install -y nginx
```

Konfigurasi Nginx:
```bash
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
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /orders {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
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

# Verifikasi via Nginx
curl http://localhost/orders
```

### 3.5 OS-Level Tuning (vm-be1 & vm-be2)

```bash
# Tambah ke /etc/sysctl.conf
sudo bash -c 'echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf'
sudo bash -c 'echo "net.ipv4.tcp_max_syn_backlog = 65535" >> /etc/sysctl.conf'
sudo sysctl -p

# Tambah ke /etc/security/limits.conf
sudo bash -c 'echo "azureuser soft nofile 65535" >> /etc/security/limits.conf'
sudo bash -c 'echo "azureuser hard nofile 65535" >> /etc/security/limits.conf'
```

Konfirmasi tuning aktif:
```bash
ulimit -n                          # → 65535
sysctl net.core.somaxconn          # → 65535
sysctl net.ipv4.tcp_max_syn_backlog # → 65535
```

### 3.6 Setup Nginx Load Balancer + Frontend (vm-lb-fe)

SSH ke vm-lb-fe:
```bash
ssh azureuser@70.153.148.59
```

Install Nginx:
```bash
sudo apt update && sudo apt install -y nginx
```

Konfigurasi Nginx sebagai Load Balancer:
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

    # Proxy API ke backend pool dengan strip prefix /api/
    location /api/ {
        rewrite ^/api(/.*)$ $1 break;
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
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

    # Serve frontend dari lokal (tidak di-forward ke backend)
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

Verifikasi end-to-end:
```bash
curl http://localhost/orders          # → []
curl http://localhost/health          # → {"status":"ok","db":"connected"}
curl http://70.153.148.59/orders     # → [] (via public IP)
```

---

## 4. Hasil Pengujian Endpoint

Pengujian dilakukan menggunakan **Postman** dengan target `http://70.153.148.59` (Load Balancer public IP).

### 4.1 POST /order — Create Order (201 Created)

Request Body:
```json
{
  "product": "Sepatu Running",
  "quantity": 2,
  "price": 150000
}
```

![POST /order 201](result/postman_post_201.png)

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

![GET /orders 200](result/postman_get_orders_200.png)

### 4.3 GET /order/\<id\> — Get Order by ID (200 OK)

![GET /order/id 200](result/postman_get_order_id_200.png)

### 4.4 GET /order/\<invalid-id\> — Order Not Found (404)

![GET 404](result/postman_get_404.png)

Response:
```json
{
  "error": "Order not found"
}
```

### 4.5 PUT /order/\<id\> — Update Order Status (200 OK)

Request Body:
```json
{
  "status": "completed"
}
```

![PUT 200](result/postman_put_200.png)

Response:
```json
{
  "order_id": "0e1f0533-5b81-4221-9231-101969c31e4e",
  "status": "completed"
}
```

### 4.6 Tampilan Frontend

![Frontend](result/frontend.png)

Frontend dapat diakses di `http://70.153.148.59`. Terhubung ke API backend melalui endpoint `/api/` yang di-strip oleh Nginx LB sebelum diteruskan ke backend pool.

---

## 5. Hasil Load Testing

Load testing dilakukan menggunakan **Locust 2.44.4** dari laptop lokal (bukan dari server) sesuai ketentuan soal.

**Konfigurasi Locust:**
```bash
locust -f Resources/Test/locustfile.py --host=http://70.153.148.59
```

**Skenario request di locustfile.py:**
| Task | Method | Endpoint | Bobot |
|------|--------|----------|-------|
| create_order | POST | /order | 50% |
| get_all_orders | GET | /orders | 30% |
| get_order_by_id | GET | /order/\<id\> | 20% |
| update_order | PUT | /order/\<id\> | 10% |

**Cleanup antar skenario:**
```bash
mongosh orders_db --eval "db.orders.deleteMany({})"
```

### 5.1 Skenario 1 — Maksimum RPS (0% Failure)

**Parameter:** User dinaikkan bertahap (50 → 100 → 200 → 300 → 400), durasi 60 detik per run

![Charts S1](result/s1_charts.png)
![Statistics S1](result/s1_statistics.png)
![htop S1](result/s1_htop.png)

**Hasil:** RPS Tertinggi = **[ISI]** RPS dengan Failure Rate **0%** pada **[ISI]** concurrent users

### 5.2 Skenario 2 — Peak Concurrency Spawn Rate 50

**Parameter:** Spawn rate tetap 50, user dinaikkan bertahap sampai failure muncul

![Charts S2](result/s2_charts.png)
![Statistics S2](result/s2_statistics.png)
![htop S2](result/s2_htop.png)

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.3 Skenario 3 — Peak Concurrency Spawn Rate 100

**Parameter:** Spawn rate tetap 100, user dinaikkan bertahap sampai failure muncul

![Charts S3](result/s3_charts.png)
![Statistics S3](result/s3_statistics.png)
![htop S3](result/s3_htop.png)
![htop S3](result/s3_htop(1).png)

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.4 Skenario 4 — Peak Concurrency Spawn Rate 200

**Parameter:** Spawn rate tetap 200, user dinaikkan bertahap sampai failure muncul

![Charts S4](result/s4_charts.png)
![Statistics S4](result/s4_statistics.png)
![htop S4](result/s4_htop.png)
![log S4](result/s4_log.png)

**Hasil:** Max Users = **[ISI]** sebelum failure muncul

### 5.5 Skenario 5 — Peak Concurrency Spawn Rate 500

**Parameter:** Spawn rate tetap 500, user dinaikkan bertahap sampai failure muncul

![Charts S5](result/s5_charts.png)
![Statistics S5](result/s5_statistics.png)
![htop S5](result/s5_htop.png)
![htop S5](result/s5_htop(1).png)
![htop S5](result/s5_htop(2).png)
![log S5](result/s5_log.png)

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

Berdasarkan hasil load testing dan monitoring resource via `htop`:

**1. GET /orders — Response Time Tinggi**
Endpoint `GET /orders` mengembalikan seluruh koleksi tanpa pagination — avg response time mencapai ~2849ms pada 50 user. Meski sudah ada index `created_at_-1`, volume data yang dikembalikan tetap menjadi bottleneck utama.

**2. Gunicorn Worker Exhaustion**
Dengan 3 Gunicorn workers per VM, sistem mulai mengalami error **502 Bad Gateway** saat concurrent user melebihi ~400. Worker queue penuh karena setiap request ke `GET /orders` memegang koneksi cukup lama.

**3. MongoDB Berbagi Resource dengan Flask**
MongoDB dan Gunicorn berjalan di vm-be1 yang sama, sehingga under heavy load keduanya berkompetisi untuk CPU dan memory. Namun dari monitoring htop, CPU usage hanya mencapai ~13% saat 200 user — mengkonfirmasi bottleneck ada di I/O dan connection handling, bukan CPU compute.

**4. Kesimpulan Bottleneck:**
`GET /orders` (no pagination) → Gunicorn worker exhaustion → 502 error. Bukan CPU-bound.

---

## 6. Kesimpulan dan Saran

### Kesimpulan

Sistem Order Processing Service berhasil di-deploy di Microsoft Azure dengan arsitektur 3 VM dan mampu melayani hingga **[ISI] RPS** dengan 0% failure rate.

Dari hasil load testing 5 skenario:
- Sistem stabil hingga **[ISI] concurrent user** dengan spawn rate bertahap (Skenario 1)
- Failure pertama muncul saat concurrent user melebihi **~400** akibat Gunicorn worker exhaustion
- Bottleneck utama bukan di CPU (max ~13%) melainkan di response time `GET /orders` yang mengembalikan seluruh koleksi tanpa batas
- Error yang muncul adalah **502 Bad Gateway** — Gunicorn kehabisan worker, bukan crash server

### Saran untuk Deployment Produksi

**1. Implementasi Pagination pada GET /orders**
```python
@app.route("/orders", methods=["GET"])
def get_orders():
    limit = int(request.args.get("limit", 50))
    skip  = int(request.args.get("skip", 0))
    docs  = list(orders.find().sort("created_at", -1).skip(skip).limit(limit))
    return jsonify([serialize(d) for d in docs]), 200
```

**2. Tambah Gunicorn Workers**
```ini
# Di systemd service, ubah ExecStart:
ExecStart=/home/azureuser/venv/bin/gunicorn \
  --workers 9 \
  --worker-connections 1000 \
  --bind 0.0.0.0:5000 app:app
```
Gunakan rumus `(2 × vCPU) + 1`.

**3. Pisahkan MongoDB ke VM Terpisah**
Menghilangkan resource contention antara MongoDB dan Flask/Gunicorn di vm-be1, meningkatkan throughput kedua layanan secara signifikan.

**4. Tambah VM Backend ke-3**
Daftarkan ke upstream Nginx LB untuk meningkatkan total Gunicorn worker capacity dari 6 menjadi 9+ worker.

**5. Implementasi Caching**
Gunakan Redis untuk cache hasil `GET /orders` dengan TTL pendek (1-5 detik) guna mengurangi beban MongoDB saat traffic spike.
