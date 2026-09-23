import json
from tools.inventory import add_product, receive_stock, query_stock, low_stock_report, list_products, update_product, lookup_by_barcode, set_barcode
from tools.billing import create_bill, add_item_to_bill, remove_item_from_bill, update_item_quantity, view_bill, finalize_bill, cancel_bill, get_bill_by_number
from tools.khata import add_credit, record_payment, get_balance, list_khata
from tools.reports import daily_close, sales_summary
from tools.memory import set_preference, get_preference, get_all_preferences
from tools.pdf_invoice import generate_invoice_pdf
from tools.pptx_deck import generate_analysis_deck

TOOLS = [
    {"name":"add_product","description":"Add new product to inventory.","input_schema":{"type":"object","properties":{"name":{"type":"string"},"sku":{"type":"string"},"unit":{"type":"string"},"is_loose":{"type":"boolean"},"cost_price":{"type":"number"},"mrp":{"type":"number"},"gst_rate":{"type":"number"},"hsn_code":{"type":"string"},"reorder_level":{"type":"number"}},"required":["name","sku","unit","is_loose","cost_price","mrp","gst_rate","hsn_code"]}},
    {"name":"receive_stock","description":"Record incoming stock for a product.","input_schema":{"type":"object","properties":{"sku_or_name":{"type":"string"},"quantity":{"type":"number"},"cost_price":{"type":"number"}},"required":["sku_or_name","quantity"]}},
    {"name":"query_stock","description":"Check stock level for a product.","input_schema":{"type":"object","properties":{"sku_or_name":{"type":"string"}},"required":["sku_or_name"]}},
    {"name":"low_stock_report","description":"List all products at or below reorder level.","input_schema":{"type":"object","properties":{}}},
    {"name":"list_products","description":"List all products or search by name.","input_schema":{"type":"object","properties":{"search":{"type":"string"}}}},
    {"name":"update_product","description":"Update price, GST or reorder level for a product.","input_schema":{"type":"object","properties":{"sku_or_name":{"type":"string"},"cost_price":{"type":"number"},"mrp":{"type":"number"},"gst_rate":{"type":"number"},"reorder_level":{"type":"number"},"hsn_code":{"type":"string"}},"required":["sku_or_name"]}},
    {"name":"lookup_by_barcode","description":"ALWAYS use this to find a product by barcode number. Never guess.","input_schema":{"type":"object","properties":{"barcode":{"type":"string"}},"required":["barcode"]}},
    {"name":"set_barcode","description":"ALWAYS use this to assign/save a barcode to a product. Never use set_preference for barcodes.","input_schema":{"type":"object","properties":{"sku_or_name":{"type":"string"},"barcode":{"type":"string"}},"required":["sku_or_name","barcode"]}},
    {"name":"create_bill","description":"Start a new draft bill.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"},"customer_name":{"type":"string"}},"required":["chat_id"]}},
    {"name":"add_item_to_bill","description":"Add a product to the active draft bill.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"},"sku_or_name":{"type":"string"},"quantity":{"type":"number"}},"required":["chat_id","sku_or_name","quantity"]}},
    {"name":"remove_item_from_bill","description":"Remove a product from the active draft bill.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"},"sku_or_name":{"type":"string"}},"required":["chat_id","sku_or_name"]}},
    {"name":"update_item_quantity","description":"Change quantity of an item in the draft bill.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"},"sku_or_name":{"type":"string"},"quantity":{"type":"number"}},"required":["chat_id","sku_or_name","quantity"]}},
    {"name":"view_bill","description":"Show current draft bill with totals.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"}},"required":["chat_id"]}},
    {"name":"finalize_bill","description":"Finalize bill, decrement stock. payment_mode: cash/upi/card.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"},"payment_mode":{"type":"string"},"payment_ref":{"type":"string"},"customer_name":{"type":"string"}},"required":["chat_id","payment_mode"]}},
    {"name":"cancel_bill","description":"Cancel the current draft bill.","input_schema":{"type":"object","properties":{"chat_id":{"type":"string"}},"required":["chat_id"]}},
    {"name":"get_bill_by_number","description":"Get a finalized bill by bill number.","input_schema":{"type":"object","properties":{"bill_number":{"type":"string"}},"required":["bill_number"]}},
    {"name":"add_credit","description":"Add khata credit for a customer.","input_schema":{"type":"object","properties":{"customer_name":{"type":"string"},"amount":{"type":"number"},"note":{"type":"string"}},"required":["customer_name","amount"]}},
    {"name":"record_payment","description":"Record khata payment from a customer.","input_schema":{"type":"object","properties":{"customer_name":{"type":"string"},"amount":{"type":"number"}},"required":["customer_name","amount"]}},
    {"name":"get_balance","description":"Get customer khata balance.","input_schema":{"type":"object","properties":{"customer_name":{"type":"string"}},"required":["customer_name"]}},
    {"name":"list_khata","description":"List all customers with outstanding balances.","input_schema":{"type":"object","properties":{}}},
    {"name":"daily_close","description":"Close the day and get sales summary.","input_schema":{"type":"object","properties":{"close_date":{"type":"string"}}}},
    {"name":"sales_summary","description":"Get sales summary for last N days.","input_schema":{"type":"object","properties":{"days":{"type":"integer"}}}},
    {"name":"set_preference","description":"Save owner preference e.g. default_payment, shop_name.","input_schema":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"}},"required":["key","value"]}},
    {"name":"get_preference","description":"Get a single owner preference.","input_schema":{"type":"object","properties":{"key":{"type":"string"}},"required":["key"]}},
    {"name":"get_all_preferences","description":"Get all owner preferences.","input_schema":{"type":"object","properties":{}}},
    {"name":"generate_invoice_pdf","description":"Generate PDF invoice for a finalized bill.","input_schema":{"type":"object","properties":{"bill_number":{"type":"string"}},"required":["bill_number"]}},
    {"name":"generate_analysis_deck","description":"Generate PPTX sales analysis deck with charts.","input_schema":{"type":"object","properties":{"days":{"type":"integer"}}}},
]

DISPATCH = {
    "add_product": lambda a: add_product(**a),
    "receive_stock": lambda a: receive_stock(**a),
    "query_stock": lambda a: query_stock(**a),
    "low_stock_report": lambda a: low_stock_report(),
    "list_products": lambda a: list_products(**a),
    "update_product": lambda a: update_product(a.pop("sku_or_name"), **a),
    "lookup_by_barcode": lambda a: lookup_by_barcode(**a),
    "set_barcode": lambda a: set_barcode(**a),
    "create_bill": lambda a: create_bill(**a),
    "add_item_to_bill": lambda a: add_item_to_bill(**a),
    "remove_item_from_bill": lambda a: remove_item_from_bill(**a),
    "update_item_quantity": lambda a: update_item_quantity(**a),
    "view_bill": lambda a: view_bill(**a),
    "finalize_bill": lambda a: finalize_bill(**a),
    "cancel_bill": lambda a: cancel_bill(**a),
    "get_bill_by_number": lambda a: get_bill_by_number(**a),
    "add_credit": lambda a: add_credit(**a),
    "record_payment": lambda a: record_payment(**a),
    "get_balance": lambda a: get_balance(**a),
    "list_khata": lambda a: list_khata(),
    "daily_close": lambda a: daily_close(**a),
    "sales_summary": lambda a: sales_summary(**a),
    "set_preference": lambda a: set_preference(**a),
    "get_preference": lambda a: get_preference(**a),
    "get_all_preferences": lambda a: get_all_preferences(),
    "generate_invoice_pdf": lambda a: generate_invoice_pdf(**a),
    "generate_analysis_deck": lambda a: generate_analysis_deck(**a),
}


def dispatch_tool(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return fn(dict(args))
    except Exception as e:
        return {"ok": False, "error": str(e)}
