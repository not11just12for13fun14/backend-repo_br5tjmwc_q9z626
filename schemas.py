"""
ERP Database Schemas

Each Pydantic model below represents a collection in MongoDB.
Collection name is the lowercase of the class name. Example:
- Product -> "product"

These schemas intentionally keep a pragmatic MVP scope so we can ship fast,
while remaining extensible for future phases.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# ---------------------------------------------------------------------
# Core & Master Data
# ---------------------------------------------------------------------

class User(BaseModel):
    name: str
    email: str
    role: Literal["admin", "sales", "purchasing", "accounting", "warehouse"] = "admin"
    is_active: bool = True

class Warehouse(BaseModel):
    name: str
    code: str = Field(..., description="Short code identifier, e.g., MAIN")
    address: Optional[str] = None
    is_active: bool = True

class Customer(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    tax_id: Optional[str] = None
    credit_limit: float = 0
    is_active: bool = True

class Supplier(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    is_active: bool = True

class Tax(BaseModel):
    name: str
    rate: float = Field(0, ge=0, description="Percentage, e.g., 5.0 for 5%")
    type: Literal["vat", "gst", "sales", "withholding", "other"] = "vat"
    is_inclusive: bool = False
    is_active: bool = True

class Product(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    uom: str = "unit"
    price: float = Field(0, ge=0)
    cost: float = Field(0, ge=0)
    tax_code: Optional[str] = None
    is_active: bool = True

# ---------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------

class InventoryTransaction(BaseModel):
    type: Literal["in", "out", "transfer", "adjustment"]
    product_sku: str
    quantity: float
    warehouse_code: str
    reference: Optional[str] = None
    notes: Optional[str] = None

class StockLevel(BaseModel):
    product_sku: str
    warehouse_code: str
    on_hand: float = 0
    reserved: float = 0

# ---------------------------------------------------------------------
# Sales & Purchasing
# ---------------------------------------------------------------------

class SalesOrderItem(BaseModel):
    product_sku: str
    quantity: float
    price: float
    tax_rate: float = 0

class SalesOrder(BaseModel):
    number: str
    customer_id: str
    order_date: datetime
    currency: str = "USD"
    items: List[SalesOrderItem]
    notes: Optional[str] = None
    status: Literal["draft", "confirmed", "delivered", "invoiced", "closed"] = "draft"

class PurchaseOrderItem(BaseModel):
    product_sku: str
    quantity: float
    cost: float
    tax_rate: float = 0

class PurchaseOrder(BaseModel):
    number: str
    supplier_id: str
    order_date: datetime
    currency: str = "USD"
    items: List[PurchaseOrderItem]
    notes: Optional[str] = None
    status: Literal["draft", "confirmed", "received", "billed", "closed"] = "draft"

class InvoiceLine(BaseModel):
    product_sku: str
    description: Optional[str] = None
    quantity: float
    unit_price: float
    tax_rate: float = 0

class Invoice(BaseModel):
    number: str
    type: Literal["sales", "purchase"]
    partner_id: str = Field(..., description="Customer ID for sales, Supplier ID for purchase")
    invoice_date: datetime
    currency: str = "USD"
    lines: List[InvoiceLine]
    status: Literal["draft", "posted", "paid", "cancelled"] = "draft"

class Payment(BaseModel):
    number: str
    type: Literal["inbound", "outbound"]
    partner_id: str
    date: datetime
    currency: str = "USD"
    amount: float
    method: str = "cash"
    reference: Optional[str] = None

# ---------------------------------------------------------------------
# Accounting
# ---------------------------------------------------------------------

class Account(BaseModel):
    code: str
    name: str
    type: Literal[
        "asset", "liability", "equity", "income", "expense",
        "receivable", "payable", "bank", "tax"
    ]
    currency: str = "USD"
    is_active: bool = True

class JournalLine(BaseModel):
    account_code: str
    debit: float = 0
    credit: float = 0
    description: Optional[str] = None

class JournalEntry(BaseModel):
    number: str
    date: datetime
    lines: List[JournalLine]
    reference: Optional[str] = None

# ---------------------------------------------------------------------
# Minimal Audit Log
# ---------------------------------------------------------------------

class AuditLog(BaseModel):
    action: str
    entity: str
    entity_id: str
    user: Optional[str] = None
    metadata: dict = {}
