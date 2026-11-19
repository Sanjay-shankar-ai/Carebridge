import os
os.environ["TESTING"] = "1"
import sys

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
print("1. Client created")

try:
    resp = client.get("/api/v1/health")
    print("2. Health response:", resp.status_code, resp.json())
except Exception as e:
    print("Health error:", e)

try:
    print("3. Calling login...")
    resp = client.post("/api/v1/auth/login", json={"email": "doctor@carebridge.com", "password": "DoctorPass123!"})
    print("4. Login response:", resp.status_code, resp.json())
except Exception as e:
    print("Login error:", e)
