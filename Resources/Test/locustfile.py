import uuid, random
from locust import HttpUser, task, between

PRODUCTS = ["Sepatu Running", "Kaos Polos", "Topi Baseball", "Tas Ransel", "Jaket Hoodie"]
_created_ids = []

class OrderUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(5)
    def create_order(self):
        payload = {
            "product": random.choice(PRODUCTS),
            "quantity": random.randint(1, 10),
            "price": random.choice([50000, 100000, 150000, 200000]),
        }
        with self.client.post("/order", json=payload, name="POST /order", catch_response=True) as r:
            if r.status_code == 201:
                data = r.json()
                if "order_id" in data:
                    _created_ids.append(data["order_id"])
                    if len(_created_ids) > 5000:
                        _created_ids.pop(0)
                r.success()
            else:
                r.failure(f"Expected 201, got {r.status_code}")

    @task(3)
    def get_all_orders(self):
        with self.client.get("/orders", name="GET /orders", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"Expected 200, got {r.status_code}")

    @task(2)
    def get_order_by_id(self):
        if not _created_ids:
            return
        oid = random.choice(_created_ids)
        with self.client.get(f"/order/{oid}", name="GET /order/<id>", catch_response=True) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"Unexpected {r.status_code}")

    @task(1)
    def update_order(self):
        if not _created_ids:
            return
        oid = random.choice(_created_ids)
        with self.client.put(f"/order/{oid}", json={"status": "processing"}, name="PUT /order/<id>", catch_response=True) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"Unexpected {r.status_code}")