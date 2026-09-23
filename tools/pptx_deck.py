import os
import tempfile
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from db import get_conn
from tools.memory import get_preference


def _add_title_slide(prs, shop_name, period):
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = f"{shop_name}"
    slide.placeholders[1].text = f"Sales Analysis — {period}"


def _add_text_slide(prs, title, lines):
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title
    tf = slide.placeholders[1].text_frame
    tf.text = lines[0] if lines else ""
    for line in lines[1:]:
        p = tf.add_paragraph()
        p.text = line


def _chart_to_image(fig, name):
    path = os.path.join(tempfile.gettempdir(), name)
    fig.savefig(path, bbox_inches="tight", dpi=120)
    plt.close(fig)
    return path


def _add_image_slide(prs, title, img_path):
    layout = prs.slide_layouts[5]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title
    slide.shapes.add_picture(img_path, Inches(0.5), Inches(1.2), Inches(9), Inches(5.5))


def generate_analysis_deck(days=7):
    conn = get_conn()
    shop_name = get_preference("shop_name")["value"] or "My Kirana Store"
    period = f"Last {days} days"

    # Data queries
    daily = conn.execute(
        """SELECT DATE(finalized_at) as day, SUM(total_amount) as revenue, SUM(total_gst) as gst, COUNT(*) as bills
           FROM bills WHERE status='finalized' GROUP BY day ORDER BY day DESC LIMIT ?""",
        (days,),
    ).fetchall()

    top_products = conn.execute(
        """SELECT p.name, SUM(bi.quantity) as qty, SUM(bi.line_total) as revenue
           FROM bill_items bi JOIN bills b ON bi.bill_id=b.id JOIN products p ON bi.product_id=p.id
           WHERE b.status='finalized' GROUP BY p.id ORDER BY revenue DESC LIMIT 8""",
    ).fetchall()

    payment_modes = conn.execute(
        """SELECT payment_mode, COUNT(*) as cnt, SUM(total_amount) as total
           FROM bills WHERE status='finalized' GROUP BY payment_mode""",
    ).fetchall()

    low_stock = conn.execute(
        "SELECT name, quantity, reorder_level FROM products WHERE quantity <= reorder_level ORDER BY quantity ASC LIMIT 8"
    ).fetchall()

    gst_collected = conn.execute(
        "SELECT SUM(total_gst) as total FROM bills WHERE status='finalized'"
    ).fetchone()

    conn.close()

    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)

    _add_title_slide(prs, shop_name, period)

    # Slide 2: Daily revenue chart
    if daily:
        days_labels = [r["day"] for r in reversed(daily)]
        revenues = [r["revenue"] for r in reversed(daily)]
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(days_labels, revenues, color="#2c3e50")
        ax.set_title("Daily Revenue (₹)")
        ax.set_ylabel("₹")
        plt.xticks(rotation=30, ha="right", fontsize=8)
        img = _chart_to_image(fig, "daily_rev.png")
        _add_image_slide(prs, "Daily Revenue", img)

    # Slide 3: Top products
    if top_products:
        names = [r["name"][:20] for r in top_products]
        revs = [r["revenue"] for r in top_products]
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.barh(names[::-1], revs[::-1], color="#27ae60")
        ax.set_title("Top Products by Revenue (₹)")
        ax.set_xlabel("₹")
        img = _chart_to_image(fig, "top_prod.png")
        _add_image_slide(prs, "Top Products", img)

    # Slide 4: Payment mode pie
    if payment_modes:
        labels = [r["payment_mode"] or "unknown" for r in payment_modes]
        sizes = [r["total"] for r in payment_modes]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=["#3498db", "#e74c3c", "#f39c12"])
        ax.set_title("Sales by Payment Mode")
        img = _chart_to_image(fig, "payment_pie.png")
        _add_image_slide(prs, "Payment Modes", img)

    # Slide 5: Stock health
    if low_stock:
        lines = [f"⚠ {r['name']}: {r['quantity']} left (reorder at {r['reorder_level']})" for r in low_stock]
        _add_text_slide(prs, "Low Stock Alert", lines)

    # Slide 6: Summary stats
    total_rev = sum(r["revenue"] for r in daily) if daily else 0
    total_gst_val = gst_collected["total"] or 0
    total_bills = sum(r["bills"] for r in daily) if daily else 0
    avg_bill = round(total_rev / total_bills, 2) if total_bills else 0
    _add_text_slide(prs, "Summary", [
        f"Total Revenue: ₹{total_rev:.2f}",
        f"Total Bills: {total_bills}",
        f"Avg Bill Value: ₹{avg_bill}",
        f"Total GST Collected: ₹{total_gst_val:.2f}",
    ])

    out_path = os.path.join(tempfile.gettempdir(), "sales_analysis.pptx")
    prs.save(out_path)
    return {"ok": True, "path": out_path}
