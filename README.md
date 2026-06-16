# Pembagian Tugas Tim (8 Orang) — Order Processing Service di GCP

## Struktur Tim
- **Divisi 1** — Infrastructure & Architecture (2 orang)
- **Divisi 2** — Backend & Database Setup (2 orang)
- **Divisi 3** — Endpoint Testing & Frontend (2 orang)
- **Divisi 4** — Load Testing & Analisis (2 orang)

---

## Tugas Bersama (Semua 8 Anggota)
- Buat GitHub repo kelompok, semua jadi collaborator
- Pemilik akun GCP tambahkan semua anggota sebagai Editor:
  `GCP Console → IAM & Admin → IAM → Grant Access → Role: Editor`
- Semua install: Google Cloud CLI, Postman, draw.io, Locust (`pip install locust`)
- Clone source code (`Resources/BE/app.py`, `Resources/FE`, `Resources/Test/locustfile.py`)

---

## 🔧 Divisi 1 — Infrastructure & Architecture

**Tanggung Jawab:** Setup project GCP, provisioning semua VM, firewall, dan Load Balancer

### D1.1 — Setup Project & Region
```bash
gcloud config set project [PROJECT_ID]
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a
```

### D1.2 — Provisioning VM
```bash
# VM Backend
gcloud compute instances create vm-backend \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --tags=http-server \
  --zone=asia-southeast1-a

# VM MongoDB
gcloud compute instances create vm-mongodb \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --tags=mongodb-server \
  --zone=asia-southeast1-a

# VM Load Balancer
gcloud compute instances create vm-loadbalancer \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB \
  --tags=http-server \
  --zone=asia-southeast1-a
```

### D1.3 — Setup Firewall Rules
```bash
# HTTP dari publik ke backend & LB
gcloud compute firewall-rules create allow-http \
  --allow=tcp:80 \
  --target-tags=http-server

# Port Flask untuk testing langsung
gcloud compute firewall-rules create allow-flask \
  --allow=tcp:5000 \
  --target-tags=http-server

# MongoDB HANYA dari VM backend (bukan publik)
gcloud compute firewall-rules create allow-mongodb-internal \
  --allow=tcp:27017 \
  --source-tags=http-server \
  --target-tags=mongodb-server
```

### D1.4 — Setup Nginx Load Balancer (di VM LB)
```bash
gcloud compute ssh vm-loadbalancer --zone=asia-southeast1-a
sudo apt update && sudo apt install -y nginx

sudo nano /etc/nginx/sites-available/loadbalancer
```
```nginx
upstream backend_pool {
    least_conn;
    server [INTERNAL_IP_VM_BACKEND]:80;
    # Tambah baris ini jika ada VM backend ke-2:
    # server [INTERNAL_IP_VM_BACKEND_2]:80;
}

server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://backend_pool;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/loadbalancer /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### D1.5 — Diagram Arsitektur (draw.io)
Komponen yang harus ada di diagram:

```
Client (Browser / Locust)
        │
        ▼
VM Load Balancer — Nginx (e2-small, external IP)
        │
        ▼
VM Backend — Flask + Gunicorn + Nginx (e2-medium)
        │
        ▼
VM MongoDB — MongoDB 7.x (e2-small, internal only)
```

- Cantumkan label: nama VM, tipe instance, IP (internal/external), port
- Export sebagai PNG untuk dimasukkan ke README

### D1.6 — Tabel Spesifikasi & Cost Breakdown

| Komponen         | Instance  | vCPU       | RAM  | Storage | Harga/Bulan |
|------------------|-----------|------------|------|---------|-------------|
| VM Load Balancer | e2-small  | 2 shared   | 2 GB | 10 GB   | ~$14        |
| VM Backend       | e2-medium | 2          | 4 GB | 20 GB   | ~$26        |
| VM MongoDB       | e2-small  | 2 shared   | 2 GB | 20 GB   | ~$14        |
| **Total**        |           |            |      |         | **~$54/bulan ✅** |

> Total di bawah budget $75 — sisa ~$21 untuk buffer eksperimen

**Output Divisi 1:** Semua VM running, LB aktif, diagram arsitektur siap, tabel biaya lengkap

---

## ⚙️ Divisi 2 — Backend & Database Setup

**Tanggung Jawab:** Install MongoDB, deploy Flask + Gunicorn + Nginx, koneksi internal antar VM

### D2.1 — Install & Konfigurasi MongoDB (di VM MongoDB)
```bash
gcloud compute ssh vm-mongodb --zone=asia-southeast1-a

curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt update && sudo apt install -y mongodb-org

# Konfigurasi bindIp ke internal IP VM backend (BUKAN 0.0.0.0)
sudo nano /etc/mongod.conf
# Ubah: bindIp: 127.0.0.1 → bindIp: 127.0.0.1,[INTERNAL_IP_VM_BACKEND]

sudo systemctl enable mongod && sudo systemctl start mongod
sudo systemctl status mongod
```

Buat index MongoDB untuk optimasi query:
```javascript
mongosh
use orders_db
db.orders.createIndex({ created_at: -1 })
db.orders.createIndex({ order_id: 1 })
```

### D2.2 — Deploy Flask + Gunicorn (di VM Backend)
```bash
gcloud compute ssh vm-backend --zone=asia-southeast1-a

sudo apt update && sudo apt install -y python3 python3-pip nginx

# Upload app.py dari lokal
gcloud compute scp Resources/BE/app.py vm-backend:~/app.py --zone=asia-southeast1-a

# Install dependencies
pip3 install flask pymongo gunicorn

# Edit koneksi MongoDB → arahkan ke internal IP VM MongoDB
nano ~/app.py
# Ganti: mongodb://localhost:27017 → mongodb://[INTERNAL_IP_VM_MONGODB]:27017
```

### D2.3 — Setup systemd Service
```bash
sudo nano /etc/systemd/system/order-api.service
```
```ini
[Unit]
Description=Order Processing API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/local/bin/gunicorn --workers 5 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable order-api && sudo systemctl start order-api
# workers = 5 karena rumus (2 × vCPU) + 1 untuk e2-medium (2 vCPU)
```

### D2.4 — Konfigurasi Nginx Reverse Proxy (di VM Backend)
```bash
sudo nano /etc/nginx/sites-available/order-app
```
```nginx
server {
    listen 80;
    server_name _;

    location / {
        root /var/www/frontend;
        index index.html;
    }

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
}
```
```bash
sudo ln -s /etc/nginx/sites-available/order-app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### D2.5 — Tuning OS-level untuk High Concurrency
```bash
sudo nano /etc/sysctl.conf
# Tambahkan:
# net.core.somaxconn = 65535
# net.ipv4.tcp_max_syn_backlog = 65535

sudo sysctl -p

sudo nano /etc/security/limits.conf
# Tambahkan:
# ubuntu soft nofile 65535
# ubuntu hard nofile 65535
```

**Output Divisi 2:** Semua endpoint live dan bisa diakses via IP Load Balancer

---

## 🧪 Divisi 3 — Endpoint Testing & Frontend

**Tanggung Jawab:** Testing semua endpoint via Postman, deploy frontend, dokumentasi screenshot

### D3.1 — Deploy Frontend (di VM Backend)
```bash
gcloud compute scp Resources/FE/index.html vm-backend:~/index.html --zone=asia-southeast1-a
gcloud compute scp Resources/FE/styles.css vm-backend:~/styles.css --zone=asia-southeast1-a

sudo mkdir -p /var/www/frontend
sudo cp ~/index.html ~/styles.css /var/www/frontend/
```

### D3.2 — Testing Endpoint via Postman

Test semua endpoint ke `http://[IP_VM_LOADBALANCER]`:

**POST /order**
```json
{
  "product": "Sepatu Running",
  "quantity": 2,
  "price": 150000
}
```
Expected response: `201 Created`

**GET /order/\<order_id\>**
- Test dengan ID valid → expected: `200 OK`
- Test dengan ID tidak ada → expected: `404 Not Found`

**GET /orders**
- Expected: `200 OK`, urutan dari terbaru

**PUT /order/\<order_id\>**
```json
{ "status": "completed" }
```
Expected response: `200 OK`

### D3.3 — Checklist Screenshot

| No | Yang Di-screenshot              | Status |
|----|----------------------------------|--------|
| 1  | POST /order → 201               | [ ]    |
| 2  | GET /order/<id> → 200           | [ ]    |
| 3  | GET /order/<id> → 404           | [ ]    |
| 4  | GET /orders → 200               | [ ]    |
| 5  | PUT /order/<id> → 200           | [ ]    |
| 6  | Frontend tampil di browser      | [ ]    |
| 7  | GCP Console — VM running        | [ ]    |

**Output Divisi 3:** Screenshot Postman semua endpoint + tampilan frontend lengkap

---

## 📊 Divisi 4 — Load Testing & Analisis

**Tanggung Jawab:** Jalankan Locust 5 skenario, monitoring resource, analisis, dan kesimpulan README

### D4.1 — Persiapan Locust (di laptop/komputer lokal — BUKAN di server)
```bash
pip install locust

# Sesuaikan host di locustfile.py ke IP VM Load Balancer
# Edit baris: host = "http://[IP_VM_LOADBALANCER]"

# Jalankan Locust
locust -f locustfile.py --host=http://[IP_VM_LOADBALANCER]
# Buka browser: http://localhost:8089
```

### D4.2 — Script Cleanup MongoDB antar Skenario
```javascript
// SSH ke vm-mongodb dulu:
// gcloud compute ssh vm-mongodb --zone=asia-southeast1-a

mongosh
use orders_db

// Hapus hanya order yang dibuat selama sesi testing
// Ganti [WAKTU_MULAI] dengan timestamp saat skenario dimulai
db.orders.deleteMany({ 
  created_at: { $gte: ISODate("[WAKTU_MULAI_SKENARIO]") } 
})

// JANGAN pakai: db.orders.deleteMany({}) — data awal tidak boleh dihapus
```

### D4.3 — 5 Skenario Pengujian

| No | Skenario              | Cara Jalankan                              | Yang Dicatat                        |
|----|-----------------------|--------------------------------------------|--------------------------------------|
| 1  | Maks RPS 0% failure   | Naik bertahap, durasi 60 detik             | RPS tertinggi saat failure = 0%      |
| 2  | Peak Concurrency SR 50  | Spawn rate 50, naikkan sampai ada failure | Max user sebelum failure             |
| 3  | Peak Concurrency SR 100 | Spawn rate 100, sama seperti atas         | Max user sebelum failure             |
| 4  | Peak Concurrency SR 200 | Spawn rate 200, sama seperti atas         | Max user sebelum failure             |
| 5  | Peak Concurrency SR 500 | Spawn rate 500, sama seperti atas         | Max user sebelum failure             |

### D4.4 — Monitoring Resource selama Testing
```bash
# SSH ke vm-backend (anggota ke-2 Divisi 4, buka terminal terpisah)
gcloud compute ssh vm-backend --zone=asia-southeast1-a

# Monitor CPU & memory real-time
htop

# Atau sampling lebih detail
vmstat 1 60   # tiap 1 detik selama 60 detik
```

### D4.5 — Checklist Screenshot per Skenario

| No | Yang Di-screenshot                    | Skenario 1 | 2 | 3 | 4 | 5 |
|----|----------------------------------------|------------|---|---|---|---|
| 1  | Grafik Locust (RPS, response time)    | [ ]        |[ ]|[ ]|[ ]|[ ]|
| 2  | Tabel statistik Locust (req, failure) | [ ]        |[ ]|[ ]|[ ]|[ ]|
| 3  | htop VM Backend (CPU & memory)        | [ ]        |[ ]|[ ]|[ ]|[ ]|

### D4.6 — Tabel Ringkasan Hasil (isi setelah testing)

| Skenario | Spawn Rate | Max Users | RPS Tertinggi | Avg Response Time | Failure Rate |
|----------|------------|-----------|---------------|-------------------|--------------|
| 1        | —          | —         | [ISI]         | [ISI]             | 0%           |
| 2        | 50         | [ISI]     | [ISI]         | [ISI]             | [ISI]        |
| 3        | 100        | [ISI]     | [ISI]         | [ISI]             | [ISI]        |
| 4        | 200        | [ISI]     | [ISI]         | [ISI]             | [ISI]        |
| 5        | 500        | [ISI]     | [ISI]         | [ISI]             | [ISI]        |

### D4.7 — Template Analisis & Kesimpulan (isi setelah data terkumpul)

```
## Analisis Hasil Load Testing

Berdasarkan hasil pengujian, sistem mampu menangani maksimum [X] RPS
dengan 0% failure rate pada skenario 1.

Bottleneck yang ditemukan:
- CPU VM Backend mencapai [X]% saat [kondisi]
- Response time meningkat signifikan saat concurrent user > [X]
- [Temuan lain dari htop/vmstat]

## Kesimpulan dan Saran

Arsitektur saat ini [cukup/tidak cukup] untuk menangani flash sale skala [X] user.

Saran scaling jika dibutuhkan:
1. Tambah VM Backend ke-2 dan daftarkan ke Nginx upstream
2. Upgrade VM Backend dari e2-medium ke e2-standard-2 jika CPU jadi bottleneck
3. Tambah replica MongoDB jika DB jadi bottleneck
```

**Output Divisi 4:** Data load testing 5 skenario lengkap, analisis bottleneck, kesimpulan README selesai

---

## Urutan Kerja & Koordinasi
```
Hari 1     → Divisi 1: Provisioning VM & firewall
             Divisi 4: Mulai tulis struktur README & template analisis

Hari 2     → Divisi 2: Deploy MongoDB + index, Flask + Gunicorn
             Divisi 1: Finalisasi diagram arsitektur & tabel biaya

Hari 3     → Divisi 2: Setup Nginx LB & tuning OS
             Divisi 3: Testing endpoint Postman + deploy frontend

Hari 4-5   → Divisi 4: Load testing 5 skenario Locust
             Divisi 4 → Divisi 2: Feedback tuning jika bottleneck ditemukan

Hari 5-6   → Divisi 4: Finalisasi analisis & kesimpulan
             Semua:    Review repo, pastikan struktur sesuai lampiran soal
```

### Alur Koordinasi Antar Divisi
```
Divisi 1 ──(VM & LB siap)──► Divisi 2
Divisi 2 ──(endpoint live)──► Divisi 3 & Divisi 4
Divisi 3 ──(screenshot)──────► Divisi 4 (untuk README)
Divisi 4 ──(bottleneck)──────► Divisi 2 (untuk tuning)
```
