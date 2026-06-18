from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os

app = Flask(__name__)

# Mengambil IP Database dari Environment Variable, default ke BE1 (10.0.0.5)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://10.0.0.5:27017/")
client = MongoClient(MONGO_URI)
db = client['cloud_orders_db']
orders_collection = db['orders']

@app.route('/api/order', methods=['POST'])
def create_order():
    try:
        data = request.json
        new_order = {
            "customer_name": data.get("customer_name"),
            "item": data.get("item"),
            "quantity": data.get("quantity", 1),
            "status": data.get("status", "Pending"),
            "created_at": datetime.utcnow()
        }
        
        result = orders_collection.insert_one(new_order)
        new_order["_id"] = str(result.inserted_id)
        
        return jsonify(new_order), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        # Mengambil semua order, diurutkan dari yang terbaru
        orders = list(orders_collection.find().sort("created_at", -1))
        for order in orders:
            order["_id"] = str(order["_id"])
        return jsonify(orders), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/order/<order_id>', methods=['GET'])
def get_order(order_id):
    try:
        order = orders_collection.find_one({"_id": ObjectId(order_id)})
        if order:
            order["_id"] = str(order["_id"])
            return jsonify(order), 200
        return jsonify({"error": "Order not found"}), 404
    except Exception:
        return jsonify({"error": "Invalid ID format"}), 400

@app.route('/api/order/<order_id>', methods=['PUT'])
def update_order(order_id):
    try:
        data = request.json
        update_data = {}
        if "status" in data:
            update_data["status"] = data["status"]
            
        result = orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0 or result.matched_count > 0:
            return jsonify({"message": "Order updated successfully"}), 200
        return jsonify({"error": "Order not found"}), 404
    except Exception:
        return jsonify({"error": "Invalid request"}), 400

# Health check endpoint untuk Load Balancer
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Berjalan di 0.0.0.0 agar bisa diakses oleh Nginx dari VM lain
    app.run(host='0.0.0.0', port=5000, debug=True)
