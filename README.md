# KazBank REST API — Python & PostgreSQL Integration

Backend service for the KazBank laboratory assignment, exposing database operations via a REST API built with Flask, PostgreSQL (`psycopg3`), and connection pooling (`psycopg-pool`).

---

## 🚀 Tech Stack
- **Python 3.10+**
- **Flask** (Web Framework)
- **PostgreSQL** (Relational Database)
- **psycopg3** (Modern PostgreSQL adapter)
- **psycopg-pool** (Connection pooling)
- **python-dotenv** (Environment variables configuration)

---

## 🛠️ Project Structure
```text
kazbank_project/
│
├── app.py              # Main Flask application, routes, pool, and error handling
├── requirements.txt    # Project dependencies
├── .env                # Database connection credentials (ignored in git)
└── README.md           # Documentation and run instructions
```

-** Sample curl Commands **

- **Start the server:**
```bash
python app.py
```

- **Health check & pool stats:**
```bash
curl.exe http://127.0.0.1:5000/health
```

- **List of clients:**
```bash
curl.exe http://127.0.0.1:5000/customers
```

- **View accounts:**
```bash
curl.exe http://127.0.0.1:5000/accounts?customer_id=1
```

- **Transfer funds:**
```bash
curl.exe -X POST http://127.0.0.1:5000/transfer -H "Content-Type: application/json" -d "{\"from_account_id\": 1, \"to_account_id\": 2, \"amount\": 5000}"
```

- **Transaction history:**
```bash
curl.exe http://127.0.0.1:5000/transactions?account_id=1
```
