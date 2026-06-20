from flask import Flask, request, jsonify
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId
import uuid
import os
from datetime import datetime, timezone

app = Flask(__name__)

# Koneksi MongoDB
# BE1 (vm-be1): MongoDB jalan lokal → MONGO_HOST=127.0.0.1
# BE2 (vm-be2): MongoDB di BE1    → MONGO_HOST=10.0.0.5
MONGO_HOST = os.environ.get("MONGO_HOST", "127.0.0.1")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))

client = MongoClient(
    host=MONGO_HOST,
    port=MONGO_PORT,
    serverSelectionTimeoutMS=3000,
)
db     = client["orders_db"]
orders = db["orders"]

def serialize(doc):
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc

# 1. Create Order - POST /order
@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body harus JSON"}), 400
    for field in ["product", "quantity", "price"]:
        if field not in data:
            return jsonify({"error": f"Field '{field}' wajib diisi"}), 400
    try:
        quantity = int(data["quantity"])
        price    = float(data["price"])
    except (ValueError, TypeError):
        return jsonify({"error": "quantity harus integer, price harus number"}), 400

    order_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc)
    doc = {
        "order_id"  : order_id,
        "product"   : str(data["product"]),
        "quantity"  : quantity,
        "price"     : price,
        "total"     : quantity * price,
        "status"    : "pending",
        "created_at": now,
    }
    orders.insert_one(doc)
    return jsonify({
        "order_id"  : order_id,
        "product"   : doc["product"],
        "quantity"  : doc["quantity"],
        "price"     : doc["price"],
        "total"     : doc["total"],
        "status"    : "pending",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }), 201

# 2. Get Order Status - GET /order/<order_id>
@app.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    doc = orders.find_one({"order_id": order_id})
    if not doc:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(serialize(doc)), 200

# 3. Get Order History - GET /orders
@app.route("/orders", methods=["GET"])
def get_orders():
    docs = list(orders.find().sort("created_at", -1))
    return jsonify([serialize(d) for d in docs]), 200

# 4. Update Order Status - PUT /order/<order_id>
@app.route("/order/<order_id>", methods=["PUT"])
def update_order(order_id):
    data = request.get_json(silent=True)
    if not data or "status" not in data:
        return jsonify({"error": "Field 'status' wajib diisi"}), 400
    allowed = {"pending", "processing", "completed", "cancelled"}
    if data["status"] not in allowed:
        return jsonify({"error": f"Status harus salah satu dari: {', '.join(allowed)}"}), 400
    result = orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": data["status"]}},
    )
    if result.matched_count == 0:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"order_id": order_id, "status": data["status"]}), 200

# Health check
@app.route("/health", methods=["GET"])
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "db": "connected"}), 200
    except ConnectionFailure:
        return jsonify({"status": "error", "db": "disconnected"}), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
