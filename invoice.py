"""
Vietnamese E-Invoice Module (Hóa đơn điện tử)
Implements invoice generation per Circular 78/2021/TT-BTC
Supports: Invoice creation, PDF generation, payment gateway integration
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import json
import psycopg2

router = APIRouter(prefix="/invoices", tags=["invoices"])

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "promptforge",
    "user": "promptforge",
    "password": "promptforge123",
}

# AI City Company Info (for invoices)
COMPANY_INFO = {
    "name": "AI City",
    "tax_id": "0123456789",
    "address": "123 Tech Street, District 1, Ho Chi Minh City, Vietnam",
    "email": "billing@aicity.vn",
    "phone": "+84 123 456 789",
}

# Vietnamese number to words conversion
def number_to_vietnamese_words(number: float) -> str:
    """Convert number to Vietnamese words for invoice"""
    if number <= 0:
        return "Không đồng"

    units = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    places = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]

    number = int(number)
    parts = []
    part_index = 0

    while number > 0:
        if number % 1000 != 0:
            three_digits = number % 1000
            word = ""

            hundreds = three_digits // 100
            tens = (three_digits % 100) // 10
            ones = three_digits % 100

            if hundreds > 0:
                word += units[hundreds] + " trăm "
                if tens == 0 and ones > 0:
                    word += "lẻ "

            if tens > 0:
                if tens == 1:
                    word += "mười "
                else:
                    word += units[tens] + " mươi "
                    if ones == 5:
                        word = word.rstrip() + " lăm "

            if ones > 0 and tens != 1:
                word += units[ones] + " "

            parts.insert(0, word.strip() + " " + places[part_index])

        number //= 1000
        part_index += 1

    result = "".join(parts).strip()
    return result + " đồng"


def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def generate_invoice_number() -> tuple:
    """Generate invoice number: INV-YYYYMM-XXXX"""
    now = datetime.now()
    year_month = now.strftime("%Y%m")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Get next sequence number for this month
    cursor.execute("""
        SELECT COUNT(*) + 1 FROM invoices
        WHERE invoice_number LIKE %s
    """, (f"INV-{year_month}-%",))

    sequence = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    invoice_number = f"INV-{year_month}-{sequence:04d}"
    invoice_serial = f"{year_month}{sequence:04d}"

    return invoice_number, invoice_serial


# ============== Models ==============

class InvoiceLineItem(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "lần"  # Service unit
    unit_price: float
    total: float


class InvoiceCreateRequest(BaseModel):
    customer_name: str
    customer_tax_id: Optional[str] = None
    customer_address: Optional[str] = None
    customer_email: Optional[str] = None

    line_items: List[InvoiceLineItem]

    payment_method: Optional[str] = None
    payment_transaction_id: Optional[str] = None

    notes: Optional[str] = None
    invoice_pattern: Optional[str] = "1/2023"


class InvoiceUpdateRequest(BaseModel):
    customer_name: Optional[str] = None
    customer_tax_id: Optional[str] = None
    customer_address: Optional[str] = None
    customer_email: Optional[str] = None
    line_items: Optional[List[InvoiceLineItem]] = None
    payment_status: Optional[str] = None
    payment_transaction_id: Optional[str] = None
    notes: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: int
    invoice_id: str
    invoice_number: str

    company_name: str
    company_tax_id: str
    company_address: str
    company_email: str
    company_phone: str

    customer_name: str
    customer_tax_id: Optional[str]
    customer_address: Optional[str]
    customer_email: Optional[str]

    subtotal: float
    vat_rate: float
    vat_amount: float
    total: float
    total_in_words: str

    payment_method: Optional[str]
    payment_status: str
    payment_transaction_id: Optional[str]

    line_items: List[dict]
    notes: Optional[str]

    invoice_pattern: Optional[str]
    tax_authority_status: str

    status: str
    issued_at: Optional[str]
    created_at: str


# ============== Helper Functions ==============

def calculate_invoice_totals(line_items: List[dict]) -> dict:
    """Calculate subtotal, VAT, and total"""
    subtotal = sum(item.get("total", 0) for item in line_items)
    vat_rate = 10.0  # Standard 10% VAT
    vat_amount = round(subtotal * vat_rate / 100, 2)
    total = subtotal + vat_amount
    total_in_words = number_to_vietnamese_words(total)

    return {
        "subtotal": subtotal,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "total": total,
        "total_in_words": total_in_words
    }


# ============== API Endpoints ==============

@router.post("/", response_model=InvoiceResponse)
async def create_invoice(request: InvoiceCreateRequest):
    """Create a new invoice"""
    try:
        # Generate invoice number
        invoice_number, invoice_serial = generate_invoice_number()
        invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

        # Calculate totals
        line_items_data = [item.dict() for item in request.line_items]
        totals = calculate_invoice_totals(line_items_data)

        # Submission deadline: 72 hours from now (per Circular 78/2021)
        submission_deadline = datetime.now() + timedelta(hours=72)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO invoices (
                invoice_id, invoice_number, invoice_serial,
                company_name, company_tax_id, company_address, company_email, company_phone,
                customer_name, customer_tax_id, customer_address, customer_email,
                subtotal, vat_rate, vat_amount, total, total_in_words,
                payment_method, payment_transaction_id,
                line_items, notes,
                invoice_pattern, submission_deadline
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
            RETURNING id, invoice_id, invoice_number, company_name, company_tax_id,
                     company_address, company_email, company_phone,
                     customer_name, customer_tax_id, customer_address, customer_email,
                     subtotal, vat_rate, vat_amount, total, total_in_words,
                     payment_method, payment_status, payment_transaction_id,
                     line_items, notes,
                     invoice_pattern, tax_authority_status,
                     status, issued_at, created_at
        """, (
            invoice_id, invoice_number, invoice_serial,
            COMPANY_INFO["name"], COMPANY_INFO["tax_id"], COMPANY_INFO["address"],
            COMPANY_INFO["email"], COMPANY_INFO["phone"],
            request.customer_name, request.customer_tax_id, request.customer_address,
            request.customer_email,
            totals["subtotal"], totals["vat_rate"], totals["vat_amount"],
            totals["total"], totals["total_in_words"],
            request.payment_method, request.payment_transaction_id,
            json.dumps(line_items_data), request.notes,
            request.invoice_pattern, submission_deadline
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return InvoiceResponse(
            id=result[0],
            invoice_id=result[1],
            invoice_number=result[2],
            company_name=result[3],
            company_tax_id=result[4],
            company_address=result[5],
            company_email=result[6],
            company_phone=result[7],
            customer_name=result[8],
            customer_tax_id=result[9],
            customer_address=result[10],
            customer_email=result[11],
            subtotal=float(result[12]),
            vat_rate=float(result[13]),
            vat_amount=float(result[14]),
            total=float(result[15]),
            total_in_words=result[16],
            payment_method=result[17],
            payment_status=result[18],
            payment_transaction_id=result[19],
            line_items=result[20],
            notes=result[21],
            invoice_pattern=result[22],
            tax_authority_status=result[23],
            status=result[24],
            issued_at=str(result[25]) if result[25] else None,
            created_at=str(result[26])
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: str):
    """Get invoice details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, invoice_id, invoice_number, company_name, company_tax_id,
                   company_address, company_email, company_phone,
                   customer_name, customer_tax_id, customer_address, customer_email,
                   subtotal, vat_rate, vat_amount, total, total_in_words,
                   payment_method, payment_status, payment_transaction_id,
                   line_items, notes,
                   invoice_pattern, tax_authority_status,
                   status, issued_at, created_at
            FROM invoices WHERE invoice_id = %s
        """, (invoice_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Invoice not found")

        return InvoiceResponse(
            id=result[0],
            invoice_id=result[1],
            invoice_number=result[2],
            company_name=result[3],
            company_tax_id=result[4],
            company_address=result[5],
            company_email=result[6],
            company_phone=result[7],
            customer_name=result[8],
            customer_tax_id=result[9],
            customer_address=result[10],
            customer_email=result[11],
            subtotal=float(result[12]),
            vat_rate=float(result[13]),
            vat_amount=float(result[14]),
            total=float(result[15]),
            total_in_words=result[16],
            payment_method=result[17],
            payment_status=result[18],
            payment_transaction_id=result[19],
            line_items=result[20],
            notes=result[21],
            invoice_pattern=result[22],
            tax_authority_status=result[23],
            status=result[24],
            issued_at=str(result[25]) if result[25] else None,
            created_at=str(result[26])
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_invoices(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    limit: int = 50
):
    """List invoices with optional filters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT id, invoice_id, invoice_number, company_name,
                   customer_name, subtotal, vat_amount, total,
                   payment_status, status, created_at
            FROM invoices WHERE 1=1
        """
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        if payment_status:
            query += " AND payment_status = %s"
            params.append(payment_status)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "invoices": [
                {
                    "id": r[0],
                    "invoice_id": r[1],
                    "invoice_number": r[2],
                    "company_name": r[3],
                    "customer_name": r[4],
                    "subtotal": float(r[5]),
                    "vat_amount": float(r[6]),
                    "total": float(r[7]),
                    "payment_status": r[8],
                    "status": r[9],
                    "created_at": str(r[10])
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{invoice_id}")
async def update_invoice(invoice_id: str, request: InvoiceUpdateRequest):
    """Update invoice"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get current invoice
        cursor.execute("""
            SELECT line_items FROM invoices WHERE invoice_id = %s
        """, (invoice_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Invoice not found")

        current_line_items = result[0]

        # Build update query
        updates = []
        values = []

        if request.customer_name is not None:
            updates.append("customer_name = %s")
            values.append(request.customer_name)
        if request.customer_tax_id is not None:
            updates.append("customer_tax_id = %s")
            values.append(request.customer_tax_id)
        if request.customer_address is not None:
            updates.append("customer_address = %s")
            values.append(request.customer_address)
        if request.customer_email is not None:
            updates.append("customer_email = %s")
            values.append(request.customer_email)
        if request.payment_status is not None:
            updates.append("payment_status = %s")
            values.append(request.payment_status)
        if request.payment_transaction_id is not None:
            updates.append("payment_transaction_id = %s")
            values.append(request.payment_transaction_id)
        if request.notes is not None:
            updates.append("notes = %s")
            values.append(request.notes)

        # Recalculate totals if line items changed
        if request.line_items is not None:
            line_items_data = [item.dict() for item in request.line_items]
            totals = calculate_invoice_totals(line_items_data)

            updates.extend([
                "line_items = %s",
                "subtotal = %s",
                "vat_rate = %s",
                "vat_amount = %s",
                "total = %s",
                "total_in_words = %s"
            ])
            values.extend([
                json.dumps(line_items_data),
                totals["subtotal"],
                totals["vat_rate"],
                totals["vat_amount"],
                totals["total"],
                totals["total_in_words"]
            ])

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(invoice_id)

        cursor.execute(f"""
            UPDATE invoices SET {', '.join(updates)}, updated_at = NOW()
            WHERE invoice_id = %s
            RETURNING id, invoice_id, status
        """, tuple(values))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "id": result[0],
            "invoice_id": result[1],
            "status": result[2],
            "message": "Invoice updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/issue")
async def issue_invoice(invoice_id: str):
    """Issue invoice (change status to issued)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE invoices
            SET status = 'issued', issued_at = NOW(), updated_at = NOW()
            WHERE invoice_id = %s AND status = 'draft'
            RETURNING id, invoice_id, invoice_number
        """, (invoice_id,))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=400, detail="Invoice not found or already issued")

        return {
            "id": result[0],
            "invoice_id": result[1],
            "invoice_number": result[2],
            "status": "issued",
            "message": "Invoice issued successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: str, reason: str = ""):
    """Cancel invoice"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE invoices
            SET status = 'cancelled',
                cancelled_at = NOW(),
                notes = COALESCE(notes || '; ', '') || 'Cancelled: ' || %s,
                updated_at = NOW()
            WHERE invoice_id = %s AND status IN ('draft', 'issued')
            RETURNING id, invoice_id, invoice_number
        """, (reason, invoice_id))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=400, detail="Invoice not found or cannot be cancelled")

        return {
            "id": result[0],
            "invoice_id": result[1],
            "invoice_number": result[2],
            "status": "cancelled",
            "message": "Invoice cancelled"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Payment Gateway Webhook Integration ==============

@router.post("/webhooks/payment")
async def payment_webhook(
    payment_id: str,
    status: str,
    transaction_id: Optional[str] = None
):
    """
    Handle payment gateway webhook
    Triggered when payment status changes
    Auto-generates invoice on successful payment
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get payment info
        cursor.execute("""
            SELECT order_id, amount, payment_method, status
            FROM payments WHERE payment_id = %s
        """, (payment_id,))

        payment = cursor.fetchone()

        if not payment:
            return {"error": "Payment not found"}

        order_id, amount, payment_method, payment_status = payment

        if status == "completed" and payment_status != "completed":
            # Payment successful - create invoice if not exists
            cursor.execute("""
                SELECT id FROM invoices
                WHERE payment_transaction_id = %s
            """, (payment_id,))

            existing = cursor.fetchone()

            if not existing:
                # Generate invoice for this payment
                invoice_number, invoice_serial = generate_invoice_number()
                invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

                # Create invoice line item from payment
                line_items = [{
                    "description": f"Payment for Order {order_id}",
                    "quantity": 1,
                    "unit": "lần",
                    "unit_price": amount,
                    "total": amount
                }]

                totals = calculate_invoice_totals(line_items)
                submission_deadline = datetime.now() + timedelta(hours=72)

                cursor.execute("""
                    INSERT INTO invoices (
                        invoice_id, invoice_number, invoice_serial,
                        company_name, company_tax_id, company_address, company_email, company_phone,
                        customer_name, customer_address,
                        subtotal, vat_rate, vat_amount, total, total_in_words,
                        payment_method, payment_status, payment_transaction_id,
                        line_items, invoice_pattern, submission_deadline,
                        status, issued_at
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        'issued', NOW()
                    )
                """, (
                    invoice_id, invoice_number, invoice_serial,
                    COMPANY_INFO["name"], COMPANY_INFO["tax_id"], COMPANY_INFO["address"],
                    COMPANY_INFO["email"], COMPANY_INFO["phone"],
                    f"Customer_{order_id[:8]}",  # Customer name from order
                    "Online Payment",
                    totals["subtotal"], totals["vat_rate"], totals["vat_amount"],
                    totals["total"], totals["total_in_words"],
                    payment_method, "paid", payment_id,
                    json.dumps(line_items), "1/2023", submission_deadline
                ))

                conn.commit()

                return {
                    "status": "invoice_created",
                    "invoice_id": invoice_id,
                    "invoice_number": invoice_number,
                    "message": "Invoice created from payment"
                }

        elif status == "refunded":
            # Update invoice payment status
            cursor.execute("""
                UPDATE invoices
                SET payment_status = 'refunded', updated_at = NOW()
                WHERE payment_transaction_id = %s
            """, (payment_id,))
            conn.commit()

        cursor.close()
        conn.close()

        return {"status": "processed"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Invoice Analytics ==============

@router.get("/analytics/revenue")
async def get_invoice_revenue():
    """Get invoice revenue analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Total invoiced
        cursor.execute("""
            SELECT COALESCE(SUM(total), 0) as total,
                   COUNT(*) as count
            FROM invoices
            WHERE status IN ('issued', 'draft')
        """)
        total_result = cursor.fetchone()

        # Paid vs pending
        cursor.execute("""
            SELECT payment_status,
                   COALESCE(SUM(total), 0) as total,
                   COUNT(*) as count
            FROM invoices
            WHERE status IN ('issued', 'draft')
            GROUP BY payment_status
        """)
        by_payment_status = [
            {"status": r[0], "total": float(r[1]), "count": r[2]}
            for r in cursor.fetchall()
        ]

        # Monthly revenue
        cursor.execute("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   COALESCE(SUM(total), 0) as total,
                   COUNT(*) as count
            FROM invoices
            WHERE status IN ('issued', 'draft')
              AND created_at >= NOW() - INTERVAL '12 months'
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month
        """)
        monthly = [
            {"month": str(r[0]), "total": float(r[1]), "count": r[2]}
            for r in cursor.fetchall()
        ]

        cursor.close()
        conn.close()

        return {
            "total_invoiced": float(total_result[0]),
            "total_invoices": total_result[1],
            "by_payment_status": by_payment_status,
            "monthly": monthly,
            "currency": "VND"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=8000)
