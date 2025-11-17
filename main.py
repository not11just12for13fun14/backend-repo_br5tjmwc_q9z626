import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
import schemas as erp_schemas

app = FastAPI(title="ERP Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "ERP Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"
    return response


# -------------------------------------------------------------
# Expose schemas for tooling/validation
# -------------------------------------------------------------

@app.get("/schema")
def get_schema_definitions():
    def model_to_dict(model_cls) -> Dict[str, Any]:
        fields = {}
        for name, field_info in model_cls.model_fields.items():
            fields[name] = {
                "type": str(field_info.annotation),
                "required": field_info.is_required(),
                "default": None if field_info.is_required() else field_info.default,
                "description": getattr(field_info, "description", None),
            }
        return {
            "collection": model_cls.__name__.lower(),
            "fields": fields,
            "doc": (model_cls.__doc__ or "").strip(),
        }

    models = {}
    for attr in dir(erp_schemas):
        obj = getattr(erp_schemas, attr)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            models[attr] = model_to_dict(obj)
    return models


# -------------------------------------------------------------
# Utilities
# -------------------------------------------------------------

def ensure_db():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")


def collection(name: str):
    ensure_db()
    return db[name]


# -------------------------------------------------------------
# Master Data Endpoints (Create + List)
# -------------------------------------------------------------

@app.post("/products")
def create_product(payload: erp_schemas.Product):
    prod = payload.model_dump()
    # Unique SKU constraint (basic)
    if collection("product").find_one({"sku": prod["sku"]}):
        raise HTTPException(status_code=400, detail="SKU already exists")
    new_id = create_document("product", prod)
    return {"id": new_id, **prod}


@app.get("/products")
def list_products():
    docs = get_documents("product")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/customers")
def create_customer(payload: erp_schemas.Customer):
    new_id = create_document("customer", payload)
    return {"id": new_id}


@app.get("/customers")
def list_customers():
    docs = get_documents("customer")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/suppliers")
def create_supplier(payload: erp_schemas.Supplier):
    new_id = create_document("supplier", payload)
    return {"id": new_id}


@app.get("/suppliers")
def list_suppliers():
    docs = get_documents("supplier")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/taxes")
def create_tax(payload: erp_schemas.Tax):
    new_id = create_document("tax", payload)
    return {"id": new_id}


@app.get("/taxes")
def list_taxes():
    docs = get_documents("tax")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/warehouses")
def create_warehouse(payload: erp_schemas.Warehouse):
    wh = payload.model_dump()
    if collection("warehouse").find_one({"code": wh["code"]}):
        raise HTTPException(status_code=400, detail="Warehouse code already exists")
    new_id = create_document("warehouse", wh)
    return {"id": new_id}


@app.get("/warehouses")
def list_warehouses():
    docs = get_documents("warehouse")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -------------------------------------------------------------
# Inventory: Transactions + Stock Levels
# -------------------------------------------------------------

class InventoryTxnRequest(erp_schemas.InventoryTransaction):
    pass


@app.post("/inventory/transactions")
def record_inventory_txn(txn: InventoryTxnRequest):
    data = txn.model_dump()
    # record transaction
    txn_id = create_document("inventorytransaction", data)

    # update stock level
    lvl = collection("stocklevel").find_one({
        "product_sku": data["product_sku"],
        "warehouse_code": data["warehouse_code"],
    })
    change = 0
    if data["type"] == "in":
        change = data["quantity"]
    elif data["type"] == "out":
        change = -data["quantity"]
    elif data["type"] == "adjustment":
        change = data["quantity"]  # positive or negative
    else:
        # transfer would be handled as two entries client-side for now
        change = 0

    if lvl:
        new_on_hand = float(lvl.get("on_hand", 0)) + float(change)
        collection("stocklevel").update_one(
            {"_id": lvl["_id"]},
            {"$set": {"on_hand": new_on_hand, "updated_at": datetime.utcnow()}},
        )
    else:
        collection("stocklevel").insert_one(
            {
                "product_sku": data["product_sku"],
                "warehouse_code": data["warehouse_code"],
                "on_hand": float(change),
                "reserved": 0.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )

    return {"id": txn_id, "applied_change": change}


@app.get("/inventory/stock")
def list_stock_levels():
    docs = get_documents("stocklevel")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -------------------------------------------------------------
# Sales Orders (basic create/list)
# -------------------------------------------------------------

@app.post("/sales/orders")
def create_sales_order(order: erp_schemas.SalesOrder):
    # ensure unique number
    if collection("salesorder").find_one({"number": order.number}):
        raise HTTPException(status_code=400, detail="Order number already exists")
    new_id = create_document("salesorder", order)
    return {"id": new_id}


@app.get("/sales/orders")
def list_sales_orders():
    docs = get_documents("salesorder")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -------------------------------------------------------------
# Invoices & Payments (basic create/list)
# -------------------------------------------------------------

@app.post("/invoices")
def create_invoice(inv: erp_schemas.Invoice):
    if collection("invoice").find_one({"number": inv.number}):
        raise HTTPException(status_code=400, detail="Invoice number already exists")
    new_id = create_document("invoice", inv)
    return {"id": new_id}


@app.get("/invoices")
def list_invoices():
    docs = get_documents("invoice")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/payments")
def create_payment(pay: erp_schemas.Payment):
    if collection("payment").find_one({"number": pay.number}):
        raise HTTPException(status_code=400, detail="Payment number already exists")
    new_id = create_document("payment", pay)
    return {"id": new_id}


@app.get("/payments")
def list_payments():
    docs = get_documents("payment")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -------------------------------------------------------------
# Dashboard Summary
# -------------------------------------------------------------

@app.get("/dashboard")
def dashboard_summary():
    ensure_db()
    totals = {
        "products": collection("product").count_documents({}),
        "customers": collection("customer").count_documents({}),
        "suppliers": collection("supplier").count_documents({}),
        "open_sales_orders": collection("salesorder").count_documents({"status": {"$in": ["draft", "confirmed"]}}),
        "invoices": collection("invoice").count_documents({}),
        "payments": collection("payment").count_documents({}),
        "stock_items": collection("stocklevel").count_documents({}),
    }
    # low stock: on_hand <= 0 or missing
    low_stock = list(collection("stocklevel").find({"on_hand": {"$lte": 0}}).limit(10))
    for x in low_stock:
        x["id"] = str(x.pop("_id"))
    return {"totals": totals, "low_stock": low_stock}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
