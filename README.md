# Pembagian Tugas Tim (8 Orang) — Order Processing Service di Azure

## Struktur Tim
- **Divisi 1** — Infrastruktur & Arsitektur (Person 1 & 2)
- **Divisi 2** — Deployment & Backend (Person 3 & 4)
- **Divisi 3** — Load Testing (Person 5 & 6)
- **Divisi 4** — Dokumentasi & Laporan (Person 7 & 8)

---

## Tugas Bersama (Semua 8 Anggota)
- Buat GitHub repo kelompok, semua jadi collaborator
- Person 1 (pemilik akun Azure for Students) tambahkan 7 anggota lain sebagai Contributor:
  `Azure Portal → Subscriptions → Access control (IAM) → Add role assignment → Role: Contributor`
- Semua install: Azure CLI, Postman, draw.io, Locust (`pip install locust`)
- Clone source code (`Resources/BE/app.py`, `Resources/FE`, `Resources/Test/locustfile.py`)

---

## 🔧 Divisi 1 — Infrastruktur & Arsitektur

**Tanggung Jawab:** Rancang arsitektur, provisioning semua resource Azure, setup jaringan & Load Balancer

### D1.1 — Rancang Arsitektur

Komponen yang digunakan:

| Komponen | Spesifikasi | Keterangan |
|----------|-------------|------------|
| VM Backend | B2s (2 vCPU, 4 GB RAM) | Jalankan Flask + Gunicorn + Nginx |
| VM MongoDB | B1s (1 vCPU, 1 GB RAM) | Database, internal only |
| Azure Load Balancer | Basic | Distribusi traffic ke VM backend |
| Network Security Group | — | Atur firewall rules |

Diagram arsitektur (buat di draw.io, export PNG):
```
Client (Browser / Locust)
        │
        ▼
Azure Load Balancer (Basic, Public IP)
        │
        ▼
VM Backend — Flask + Gunicorn + Nginx (B2s, Southeast Asia)
        │
        ▼
VM MongoDB — MongoDB 7.x (B1s, internal only)
```

- Cantumkan label: nama VM, tipe instance, IP (privat/publik), port yang digunakan
- Sertakan frontend (serve via Nginx di VM backend yang sama)

### D1.2 — Tabel Spesifikasi & Cost Breakdown

| Komponen | Instance | vCPU | RAM | Storage | Harga/Bulan |
|----------|----------|------|-----|---------|-------------|
| VM Backend | B2s | 2 | 4 GB | 30 GB | ~$35 |
| VM MongoDB | B1s | 1 | 1 GB | 30 GB | ~$15 |
| Azure Load Balancer | Basic | — | — | — | ~$18 |
| **Total** | | | | | **~$68/bulan ✅** |

> Total di bawah budget $75 (~Rp1.3 juta) — sisa ~$7 untuk buffer

Tulis justifikasi:
- Kenapa B2s untuk backend: 2 vCPU dedicated cukup untuk handle Gunicorn multi-worker
- Kenapa B1s untuk MongoDB: DB tidak kena traffic langsung, burstable CPU cukup
- Kenapa Load Balancer Basic: budget terbatas, fitur Basic sudah cukup untuk FP ini
- Trade-off: B1s burstable CPU bisa throttle jika terus-menerus dipakai intensif

### D1.3 — Provisioning Resource Azure

Login dan set subscription:
```bash
az login
az account set --subscription "[SUBSCRIPTION_ID]"
```

Buat Resource Group:
```bash
az group create \
  --name rg-order-processing \
  --location southeastasia
```

Buat VM Backend:
```bash
az vm create \
  --resource-group rg-order-processing \
  --name vm-backend \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Basic \
  --location southeastasia
```

Buat VM MongoDB:
```bash
az vm create \
  --resource-group rg-order-processing \
  --name vm-mongodb \
  --image Ubuntu2204 \
  --size Standard_B1s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Basic \
  --location southeastasia
```

### D1.4 — Setup Network Security Group

Buka port 80 untuk HTTP publik (VM Backend):
```bash
az vm open-port \
  --resource-group rg-order-processing \
  --name vm-backend \
  --port 80 \
  --priority 1001
```

Buka port 5000 untuk Flask (testing langsung):
```bash
az vm open-port \
  --resource-group rg-order-processing \
  --name vm-backend \
  --port 5000 \
  --priority 1002
```

Restrict MongoDB port 27017 hanya dari VM backend (via Azure Portal):
```
Azure Portal → vm-mongodb → Networking → Add inbound port rule:
  - Source: IP Addresses
  - Source IP: [PRIVATE_IP_VM_BACKEND]
  - Destination port: 27017
  - Protocol: TCP
  - Priority: 1001
  - Name: allow-mongodb-from-backend
```

### D1.5 — Setup Azure Load Balancer Basic

Buat Public IP untuk Load Balancer:
```bash
az network public-ip create \
  --resource-group rg-order-processing \
  --name lb-public-ip \
  --sku Basic \
  --allocation-method Static
```

Buat Load Balancer:
```bash
az network lb create \
  --resource-group rg-order-processing \
  --name lb-order \
  --sku Basic \
  --public-ip-address lb-public-ip \
  --frontend-ip-name lb-frontend \
  --backend-pool-name lb-backend-pool
```

Buat Health Probe:
```bash
az network lb probe create \
  --resource-group rg-order-processing \
  --lb-name lb-order \
  --name health-probe-http \
  --protocol Http \
  --port 80 \
  --path /orders
```

Buat Load Balancing Rule:
```bash
az network lb rule create \
  --resource-group rg-order-processing \
  --lb-name lb-order \
  --name lb-rule-http \
  --protocol Tcp \
  --frontend-port 80 \
  --backend-port 80 \
  --frontend-ip-name lb-frontend \
  --backend-pool-name lb-backend-pool \
  --probe-name health-probe-http
```

Daftarkan NIC VM Backend ke backend pool:
```bash
# Dapatkan NIC name VM backend dulu
az vm nic list \
  --resource-group rg-order-processing \
  --vm-name vm-backend

# Update NIC agar masuk ke backend pool
az network nic ip-config update \
  --resource-group rg-order-processing \
  --nic-name [NIC_NAME_VM_BACKEND] \
  --name ipconfig1 \
  --lb-name lb-order \
  --lb-address-pool lb-backend-pool
```

**Output Divisi 1:** Semua VM running, Load Balancer aktif & healthy, diagram arsitektur siap, tabel biaya lengkap

---

## ⚙️ Divisi 2 — Deployment & Backend

**Tanggung Jawab:** Install MongoDB, deploy Flask + Gunicorn + Nginx, koneksi internal antar VM, testing fungsional endpoint

### D2.1 — Install & Konfigurasi MongoDB (di VM MongoDB)

SSH ke VM MongoDB:
```bash
ssh azureuser@[PUBLIC_IP_VM_MONGODB]
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

Konfigurasi bindIp ke private IP VM backend (BUKAN 0.0.0.0):
```bash
sudo nano /etc/mongod.conf
# Ubah baris bindIp:
# bindIp: 127.0.0.1 → bindIp: 127.0.0.1,[PRIVATE_IP_VM_BACKEND]
```

Start & enable MongoDB:
```bash
sudo systemctl enable mongod && sudo systemctl start mongod
sudo systemctl status mongod
```

Buat index untuk optimasi query:
```javascript
mongosh
use orders_db
db.orders.createIndex({ created_at: -1 })
db.orders.createIndex({ order_id: 1 })
```

### D2.2 — Deploy Flask + Gunicorn (di VM Backend)

SSH ke VM Backend:
```bash
ssh azureuser@[PUBLIC_IP_VM_BACKEND]
```

Install dependencies:
```bash
sudo apt update && sudo apt install -y python3 python3-pip nginx
```

Upload app.py dari lokal:
```bash
scp Resources/BE/app.py azureuser@[PUBLIC_IP_VM_BACKEND]:~/app.py
```

Install Python packages:
```bash
pip3 install flask pymongo gunicorn
```

Edit koneksi MongoDB di app.py → arahkan ke private IP VM MongoDB:
```bash
nano ~/app.py
# Ganti: mongodb://localhost:27017
# Jadi:  mongodb://[PRIVATE_IP_VM_MONGODB]:27017
```

### D2.3 — Setup systemd Service untuk Gunicorn

```bash
sudo nano /etc/systemd/system/order-api.service
```

```ini
[Unit]
Description=Order Processing API
After=network.target

[Service]
User=azureuser
WorkingDirectory=/home/azureuser
ExecStart=/usr/local/bin/gunicorn --workers 5 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable order-api && sudo systemctl start order-api
sudo systemctl status order-api
# workers = 5 karena rumus (2 × vCPU) + 1 untuk B2s (2 vCPU)
```

### D2.4 — Deploy Frontend + Konfigurasi Nginx

Upload file frontend:
```bash
scp Resources/FE/index.html azureuser@[PUBLIC_IP_VM_BACKEND]:~/index.html
scp Resources/FE/styles.css azureuser@[PUBLIC_IP_VM_BACKEND]:~/styles.css

sudo mkdir -p /var/www/frontend
sudo cp ~/index.html ~/styles.css /var/www/frontend/
```

Sesuaikan API base URL di index.html ke alamat Load Balancer:
```bash
nano /var/www/frontend/index.html
# Ganti API base URL ke: http://[PUBLIC_IP_LOAD_BALANCER]
```

Konfigurasi Nginx sebagai reverse proxy + serve frontend:
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
# azureuser soft nofile 65535
# azureuser hard nofile 65535
```

### D2.6 — Testing Fungsional via Postman

Test semua endpoint ke `http://[PUBLIC_IP_LOAD_BALANCER]`:

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
- ID valid → expected: `200 OK`
- ID tidak ada → expected: `404 Not Found`

**GET /orders**
- Expected: `200 OK`, urutan dari terbaru

**PUT /order/\<order_id\>**
```json
{ "status": "completed" }
```
Expected response: `200 OK`

### D2.7 — Checklist Screenshot Divisi 2

| No | Yang Di-screenshot | Status |
|----|-------------------|--------|
| 1 | POST /order → 201 | [ ] |
| 2 | GET /order/\<id\> → 200 | [ ] |
| 3 | GET /order/\<id\> → 404 | [ ] |
| 4 | GET /orders → 200 | [ ] |
| 5 | PUT /order/\<id\> → 200 | [ ] |
| 6 | Frontend tampil di browser & semua fitur jalan | [ ] |
| 7 | Azure Portal — VM running | [ ] |
| 8 | Azure Portal — Load Balancer healthy | [ ] |

**Output Divisi 2:** Semua endpoint live via Load Balancer, frontend accessible, screenshot Postman lengkap

---

## 📊 Divisi 3 — Load Testing

**Tanggung Jawab:** Jalankan Locust 5 skenario dari komputer lokal, monitoring resource VM, cleanup data antar skenario

### D3.1 — Persiapan Locust (di laptop/komputer lokal — BUKAN di server)

```bash
pip install locust

# Sesuaikan target host di locustfile.py ke IP Load Balancer
# Edit baris: host = "http://[PUBLIC_IP_LOAD_BALANCER]"

# Jalankan Locust
locust -f locustfile.py --host=http://[PUBLIC_IP_LOAD_BALANCER]
# Buka browser: http://localhost:8089
```

### D3.2 — Script Cleanup MongoDB antar Skenario

Jalankan setelah setiap skenario selesai:
```javascript
// SSH ke vm-mongodb dulu:
// ssh azureuser@[PUBLIC_IP_VM_MONGODB]

mongosh
use orders_db

// Hapus hanya order yang dibuat selama sesi testing
// Ganti [WAKTU_MULAI] dengan timestamp ISO saat skenario dimulai
db.orders.deleteMany({
  created_at: { $gte: ISODate("[WAKTU_MULAI_SKENARIO]") }
})

// JANGAN pakai: db.orders.deleteMany({}) — data awal tidak boleh dihapus
```

### D3.3 — 5 Skenario Pengujian

| No | Skenario | Cara Jalankan | Yang Dicatat |
|----|----------|---------------|--------------|
| 1 | Maks RPS 0% failure | Naik bertahap, durasi 60 detik | RPS tertinggi saat failure = 0% |
| 2 | Peak Concurrency SR 50 | Spawn rate 50, naikkan sampai ada failure | Max user sebelum failure |
| 3 | Peak Concurrency SR 100 | Spawn rate 100, sama seperti atas | Max user sebelum failure |
| 4 | Peak Concurrency SR 200 | Spawn rate 200, sama seperti atas | Max user sebelum failure |
| 5 | Peak Concurrency SR 500 | Spawn rate 500, sama seperti atas | Max user sebelum failure |

### D3.4 — Monitoring Resource selama Testing

Opsi 1 — htop di VM Backend (buka terminal terpisah):
```bash
ssh azureuser@[PUBLIC_IP_VM_BACKEND]
htop
```

Opsi 2 — vmstat untuk sampling lebih detail:
```bash
vmstat 1 60   # sampling tiap 1 detik selama 60 detik
```

Opsi 3 — Azure Monitor (via portal):
```
Azure Portal → vm-backend → Monitoring → Metrics
→ Pilih: Percentage CPU, Available Memory Bytes
→ Screenshot grafik tiap skenario
```

### D3.5 — Checklist Screenshot per Skenario

| No | Yang Di-screenshot | S1 | S2 | S3 | S4 | S5 |
|----|-------------------|----|----|----|----|-----|
| 1 | Grafik Locust (RPS, response time) | [ ] | [ ] | [ ] | [ ] | [ ] |
| 2 | Tabel statistik Locust (req, failure) | [ ] | [ ] | [ ] | [ ] | [ ] |
| 3 | htop / Azure Monitor (CPU & memory) | [ ] | [ ] | [ ] | [ ] | [ ] |

### D3.6 — Tabel Ringkasan Hasil (isi setelah testing)

| Skenario | Spawn Rate | Max Users | RPS Tertinggi | Avg Response Time | Failure Rate |
|----------|------------|-----------|---------------|-------------------|--------------|
| 1 | — | — | [ISI] | [ISI] | 0% |
| 2 | 50 | [ISI] | [ISI] | [ISI] | [ISI] |
| 3 | 100 | [ISI] | [ISI] | [ISI] | [ISI] |
| 4 | 200 | [ISI] | [ISI] | [ISI] | [ISI] |
| 5 | 500 | [ISI] | [ISI] | [ISI] | [ISI] |

**Output Divisi 3:** Screenshot 5 skenario lengkap (grafik Locust + htop/Azure Monitor), tabel ringkasan hasil terisi

---

## 📝 Divisi 4 — Dokumentasi & Laporan

**Tanggung Jawab:** Tulis laporan Markdown lengkap di README.md, konsolidasi semua output dari divisi lain

### D4.1 — Struktur README.md

```
# Order Processing Service — Final Project Cloud Engineering

## 1. Introduction
## 2. Arsitektur Cloud
## 3. Implementasi
## 4. Hasil Pengujian Endpoint
## 5. Hasil Load Testing
## 6. Kesimpulan dan Saran
```

### D4.2 — Panduan Penulisan per Bagian

**Bagian 1 — Introduction**
- Latar belakang masalah: kenapa perlu cloud untuk order processing
- Ringkasan singkat dari soal FP
- Bisa dikerjakan dari hari pertama tanpa menunggu divisi lain

**Bagian 2 — Arsitektur Cloud**
- Ambil diagram PNG dari Divisi 1 → `![Arsitektur](diagram.png)`
- Ambil tabel spesifikasi & cost breakdown dari Divisi 1
- Tulis justifikasi pemilihan konfigurasi (kenapa B2s, kenapa LB Basic, dll)

**Bagian 3 — Implementasi**
- Minta step-by-step konfigurasi dari Divisi 1 & 2
- Susun jadi langkah runtut dengan penjelasan singkat tiap step
- Sertakan screenshot: Azure Portal VM running, LB healthy, terminal saat deploy

**Bagian 4 — Hasil Pengujian Endpoint**
- Ambil screenshot Postman dari Divisi 2
- Ambil screenshot frontend dari Divisi 2
- Susun per endpoint dengan penjelasan singkat

**Bagian 5 — Hasil Load Testing**
- Ambil data & screenshot dari Divisi 3
- Masukkan tabel ringkasan 5 skenario (D3.6)
- Tulis analisis bottleneck:

```
Analisis Hasil Load Testing

Berdasarkan hasil pengujian, sistem mampu menangani maksimum [X] RPS
dengan 0% failure rate pada skenario 1.

Bottleneck yang ditemukan:
- CPU VM Backend mencapai [X]% saat concurrent user > [X]
- Response time meningkat signifikan saat spawn rate tinggi
- [Temuan lain dari htop/Azure Monitor]
```

**Bagian 6 — Kesimpulan dan Saran**

```
Kesimpulan dan Saran

Arsitektur saat ini [cukup/tidak cukup] untuk menangani flash sale
skala [X] concurrent user.

Saran scaling untuk deployment produksi:
1. Tambah VM Backend ke-2 dan daftarkan ke Load Balancer backend pool
2. Upgrade VM Backend dari B2s ke B4ms jika CPU jadi bottleneck
3. Gunakan Azure Database for MongoDB (managed) untuk HA & backup otomatis
4. Aktifkan Azure Autoscale jika traffic tidak predictable
```

### D4.3 — Checklist Dokumentasi

| No | Bagian | Status |
|----|--------|--------|
| 1 | Introduction selesai | [ ] |
| 2 | Diagram arsitektur masuk README | [ ] |
| 3 | Tabel biaya masuk README | [ ] |
| 4 | Step implementasi lengkap + screenshot | [ ] |
| 5 | Screenshot Postman semua endpoint | [ ] |
| 6 | Screenshot frontend di browser | [ ] |
| 7 | Tabel ringkasan 5 skenario Locust terisi | [ ] |
| 8 | Screenshot grafik Locust semua skenario | [ ] |
| 9 | Analisis bottleneck ditulis | [ ] |
| 10 | Kesimpulan & saran ditulis | [ ] |
| 11 | Struktur repo sesuai lampiran soal | [ ] |

**Output Divisi 4:** README.md final lengkap, repo GitHub rapi dan siap dinilai

---

## Urutan Kerja & Koordinasi

```
Hari 1     → Divisi 1: Provisioning VM & NSG di Azure
             Divisi 4: Tulis bagian Introduction & struktur README

Hari 2     → Divisi 1: Setup Load Balancer, finalisasi diagram & tabel biaya
             Divisi 2: Deploy MongoDB + index (tunggu VM dari Divisi 1)

Hari 3     → Divisi 2: Deploy Flask + Gunicorn + Nginx, frontend, tuning OS
             Divisi 4: Tulis bagian Arsitektur Cloud dari output Divisi 1

Hari 4     → Divisi 3: Testing endpoint Postman (tunggu Divisi 2 selesai)
             Divisi 4: Susun bagian Implementasi dari output Divisi 1 & 2

Hari 4-5   → Divisi 3: Load testing 5 skenario Locust
             Divisi 3 → Divisi 2: Feedback tuning jika bottleneck ditemukan

Hari 5-6   → Divisi 4: Konsolidasi semua output, tulis analisis & kesimpulan
             Semua:    Review README, pastikan struktur repo sesuai lampiran soal
```

### Alur Koordinasi Antar Divisi

```
Divisi 1 ──(VM & LB siap)────► Divisi 2
Divisi 2 ──(endpoint live)───► Divisi 3
Divisi 2 ──(screenshot)──────► Divisi 4
Divisi 3 ──(data & screenshot)► Divisi 4
Divisi 3 ──(bottleneck)──────► Divisi 2 (untuk tuning)
Divisi 4 ──(README draft)────► Semua (untuk review)
```
