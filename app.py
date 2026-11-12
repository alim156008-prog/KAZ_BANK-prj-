import os
import time
from flask import Flask, request, jsonify
import psycopg
from psycopg import errors as pg_errors
from psycopg import IsolationLevel
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# (R3: min=2, max=8)
DATABASE_URL = os.environ.get("DATABASE_URL")
pool = ConnectionPool(conninfo=DATABASE_URL, min_size=2, max_size=8, timeout=5.0)

# R1
def init_db():
    DDL = """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id SERIAL PRIMARY KEY,
        full_name   TEXT NOT NULL,
        city        TEXT DEFAULT 'Almaty',
        email       TEXT UNIQUE
    );
    CREATE TABLE IF NOT EXISTS accounts (
        account_id  SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(customer_id) ON DELETE CASCADE,
        balance     NUMERIC(15,2) DEFAULT 0 CHECK (balance >= 0)
    );
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id SERIAL PRIMARY KEY,
        account_id     INTEGER REFERENCES accounts(account_id),
        amount         NUMERIC(15,2) NOT NULL,
        tx_type        TEXT NOT NULL
    );
    """
    with pool.connection() as conn:
        conn.execute(DDL)
        conn.commit()

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM customers")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO customers (full_name, city, email) VALUES (%s, %s, %s)",
                [
                    ("Arman Bekov", "Almaty", "arman@example.com"),
                    ("Zarina Seiit", "Astana", "zarina@example.com"),
                ]
            )
            cur.executemany(
                "INSERT INTO accounts (customer_id, balance) VALUES (%s, %s)",
                [
                    (1, 100000.00),
                    (2, 50000.00),
                ]
            )
            conn.commit()
    print("Database schema initialized and seeded.")
    
with app.app_context():
    init_db()


#R5
def with_retry(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn()
        except psycopg.errors.SerializationFailure:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


# R2

@app.route("/health", methods=["GET"])
def health():
    #R8
    try:
        pool.check()
        stats = pool.get_stats()
        return jsonify({"status": "ok", "stats": stats}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


@app.route("/customers", methods=["GET"])
def list_customers():
    city = request.args.get("city")
    with pool.connection() as conn:
        if city:
            rows = conn.execute(
                "SELECT customer_id, full_name, city, email FROM customers WHERE city = %s ORDER BY customer_id",
                (city,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT customer_id, full_name, city, email FROM customers ORDER BY customer_id"
            ).fetchall()
    return jsonify([{"id": r[0], "name": r[1], "city": r[2], "email": r[3]} for r in rows]), 200


@app.route("/customers", methods=["POST"])
def create_customer():
    """R6: Обработка ошибок UniqueViolation, NotNullViolation"""
    data = request.get_json(force=True)
    try:
        with pool.connection() as conn:
            cur = conn.execute(
                "INSERT INTO customers (full_name, city, email) VALUES (%s, %s, %s) RETURNING customer_id",
                (data.get("full_name"), data.get("city", "Almaty"), data.get("email"))
            )
            new_id = cur.fetchone()[0]
            conn.commit()
        return jsonify({"customer_id": new_id}), 201

    except pg_errors.UniqueViolation:
        return jsonify({"error": "Email already registered"}), 409
    except pg_errors.NotNullViolation as e:
        return jsonify({"error": f"Missing required field: {e.diag.column_name}"}), 400
    except psycopg.OperationalError:
        return jsonify({"error": "Database unavailable"}), 503


@app.route("/accounts", methods=["GET"])
def list_accounts():
    customer_id = request.args.get("customer_id")
    with pool.connection() as conn:
        if customer_id:
            rows = conn.execute(
                "SELECT account_id, customer_id, balance FROM accounts WHERE customer_id = %s",
                (customer_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT account_id, customer_id, balance FROM accounts").fetchall()
    return jsonify([{"account_id": r[0], "customer_id": r[1], "balance": float(r[2])} for r in rows]), 200


@app.route("/transactions", methods=["GET"])
def list_transactions():
    account_id = request.args.get("account_id")
    with pool.connection() as conn:
        if account_id:
            rows = conn.execute(
                "SELECT transaction_id, account_id, amount, tx_type FROM transactions WHERE account_id = %s",
                (account_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT transaction_id, account_id, amount, tx_type FROM transactions").fetchall()
    return jsonify([{"transaction_id": r[0], "account_id": r[1], "amount": float(r[2]), "tx_type": r[3]} for r in rows]), 200


@app.route("/transfer", methods=["POST"])
def transfer_funds():
    """R4, R5: Атомичный перевод с уровнем SERIALIZABLE и защитой от дедлоков (сортировка ID)"""
    data = request.get_json(force=True)
    from_acc = data["from_account_id"]
    to_acc = data["to_account_id"]
    amount = data["amount"]

    def _execute_transfer():
        with pool.connection() as conn:
            # R5
            conn.isolation_level = IsolationLevel.SERIALIZABLE
        
            first, second = sorted([from_acc, to_acc])
            conn.execute("SELECT 1 FROM accounts WHERE account_id = %s FOR UPDATE", (first,))
            conn.execute("SELECT 1 FROM accounts WHERE account_id = %s FOR UPDATE", (second,))

            cur = conn.execute("SELECT balance FROM accounts WHERE account_id = %s", (from_acc,))
            row = cur.fetchone()
            if not row or row[0] < amount:
                raise ValueError("Insufficient funds or account not found")

            # R4: 
            conn.execute(
                "UPDATE accounts SET balance = balance - %s WHERE account_id = %s",
                (amount, from_acc)
            )
            conn.execute(
                "UPDATE accounts SET balance = balance + %s WHERE account_id = %s",
                (amount, to_acc)
            )
            conn.execute(
                "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
                (from_acc, -amount, "DEBIT")
            )
            conn.execute(
                "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
                (to_acc, amount, "CREDIT")
            )
            conn.commit()

    try:
        with_retry(_execute_transfer)
        return jsonify({"status": "success", "message": "Transfer completed successfully"}), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)