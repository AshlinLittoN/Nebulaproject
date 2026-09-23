import os
import tempfile
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from tools.billing import get_bill_by_number
from tools.memory import get_preference


def generate_invoice_pdf(bill_number):
    bill = get_bill_by_number(bill_number)
    if not bill["ok"]:
        return {"ok": False, "error": bill["error"]}

    shop_name = get_preference("shop_name")["value"] or "My Kirana Store"
    shop_gstin = get_preference("shop_gstin")["value"] or "N/A"
    shop_address = get_preference("shop_address")["value"] or ""

    out_path = os.path.join(tempfile.gettempdir(), f"{bill_number}.pdf")
    doc = SimpleDocTemplate(out_path, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    bold = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold")
    center = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)
    center_bold = ParagraphStyle("center_bold", parent=styles["Normal"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=14)

    story = []
    story.append(Paragraph(shop_name, center_bold))
    story.append(Paragraph(shop_address, center))
    story.append(Paragraph(f"GSTIN: {shop_gstin}", center))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("TAX INVOICE", ParagraphStyle("ti", parent=styles["Normal"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=12)))
    story.append(Spacer(1, 3*mm))

    meta = [
        [Paragraph(f"<b>Invoice No:</b> {bill['bill_number']}", styles["Normal"]),
         Paragraph(f"<b>Date:</b> {bill['created_at'][:10]}", ParagraphStyle("r", parent=styles["Normal"], alignment=TA_RIGHT))],
        [Paragraph(f"<b>Customer:</b> {bill['customer'] or 'Walk-in'}", styles["Normal"]),
         Paragraph(f"<b>Payment:</b> {(bill['payment_mode'] or '').upper()}", ParagraphStyle("r", parent=styles["Normal"], alignment=TA_RIGHT))],
    ]
    meta_table = Table(meta, colWidths=[90*mm, 90*mm])
    story.append(meta_table)
    story.append(Spacer(1, 4*mm))

    # Items table
    headers = ["#", "Item", "HSN", "Qty", "Unit", "Rate (₹)", "GST%", "GST (₹)", "Total (₹)"]
    rows = [headers]
    for i, item in enumerate(bill["items"], 1):
        rows.append([
            str(i), item["name"], item["hsn"],
            str(item["qty"]), item["unit"],
            f"{item['unit_price']:.2f}", f"{item['gst_rate']}%",
            f"{item['gst_amount']:.2f}", f"{item['line_total']:.2f}",
        ])

    col_widths = [8*mm, 50*mm, 15*mm, 12*mm, 12*mm, 18*mm, 12*mm, 18*mm, 18*mm]
    item_table = Table(rows, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 4*mm))

    # GST breakup
    gst_rows = [["GST Rate", "Taxable (₹)", "CGST (₹)", "SGST (₹)", "Total GST (₹)"]]
    for rate, vals in bill["gst_breakup"].items():
        if rate == 0:
            continue
        gst_rows.append([
            f"{rate}%", f"{vals['taxable']:.2f}",
            f"{vals['cgst']:.2f}", f"{vals['sgst']:.2f}",
            f"{vals['cgst']+vals['sgst']:.2f}",
        ])
    if len(gst_rows) > 1:
        gst_table = Table(gst_rows, colWidths=[25*mm, 35*mm, 30*mm, 30*mm, 35*mm])
        gst_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(Paragraph("<b>GST Breakup (Intra-state: CGST + SGST)</b>", styles["Normal"]))
        story.append(Spacer(1, 2*mm))
        story.append(gst_table)
        story.append(Spacer(1, 4*mm))

    # Totals
    totals = [
        ["Subtotal (excl. GST)", f"₹{bill['subtotal']:.2f}"],
        ["Total GST", f"₹{bill['total_gst']:.2f}"],
        ["TOTAL PAYABLE", f"₹{bill['total_amount']:.2f}"],
    ]
    tot_table = Table(totals, colWidths=[130*mm, 50*mm])
    tot_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, 2), 11),
        ("LINEABOVE", (0, 2), (-1, 2), 1, colors.black),
    ]))
    story.append(tot_table)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Thank you for shopping with us!", center))

    doc.build(story)
    return {"ok": True, "path": out_path, "bill_number": bill_number}
