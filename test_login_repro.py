import requests

tests = [
    ("doctor@carebridge.com", "DoctorPass123!"),
    ("Doctor@CareBridge.com", "DoctorPass123!"),
    (" doctor@carebridge.com ", "DoctorPass123!"),
    ("coordinator@carebridge.com", "CoordinatorPass123!"),
    ("COORDINATOR@CAREBRIDGE.COM", "CoordinatorPass123!"),
    (" coordinator@carebridge.com ", "CoordinatorPass123!"),
    ("patient@carebridge.com", "PatientPass123!"),
    ("Patient@CareBridge.com", "PatientPass123!"),
    (" patient@carebridge.com ", "PatientPass123!"),
    ("aris.thorne@specialtyclinic.org", "DoctorPass123!"),
    ("priya.nair@metrogovhealth.org", "CoordinatorPass123!"),
    ("meenakshi.r52@example.com", "PatientPass123!"),
    ("doctor@carebridge.com", "WrongPass!"),
    ("patient@carebridge.com", "WrongPass!"),
]

for email, pwd in tests:
    try:
        r = requests.post("http://127.0.0.1:8000/api/v1/auth/login", json={"email": email, "password": pwd}, timeout=5)
        status = r.status_code
        body = r.json() if "application/json" in r.headers.get("content-type", "") else {"text": r.text}
        msg = body.get("message") or body.get("detail") or str(body)
        data = body.get("data", {})
        role = data.get("role") if isinstance(data, dict) else None
        print(f"{email:<35} | Status: {status} | Role: {str(role):<16} | Msg: {msg}")
    except Exception as e:
        print(f"{email:<35} | Error: {e}")
