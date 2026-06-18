# Deployment Notes - Person A (Divisi 2)

## D2.1 - MongoDB Setup (BE1: 70.153.149.199)
- MongoDB 7.x berhasil diinstall
- bindIp dikonfigurasi: 127.0.0.1,10.0.0.5
- Service mongod: active (running) & enabled
- Index created: created_at (-1), order_id (1)

## D2.2 - Flask + Gunicorn (BE1 & BE2)
- Python venv dibuat di kedua server
- Library terinstall: flask, pymongo, gunicorn
- app.py berhasil dideploy ke BE1 & BE2
- MongoDB URI: mongodb://10.0.0.5:27017/

## D2.3 - Systemd Service (BE1 & BE2)
- Service: order-api.service
- Workers: 3 (rumus 2x vCPU + 1)
- Port: 5000
- Status: active (running) & enabled di kedua server

## D2.5 - OS Tuning (BE1 & BE2)
- net.core.somaxconn = 65535
- net.ipv4.tcp_max_syn_backlog = 65535
- azureuser nofile soft/hard = 65535