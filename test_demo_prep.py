import requests
import json

base_url = "http://localhost:8000/api/v1"

accounts = {
    "doctor": ("doctor@carebridge.com", "DoctorPass123!"),
    "coordinator": ("coordinator@carebridge.com", "CoordinatorPass123!"),
    "patient": ("patient@carebridge.com", "PatientPass123!"),
}

tokens = {}

print("=== 1. Testing Demo Logins ===")
for role, (email, pwd) in accounts.items():
    res = requests.post(f"{base_url}/auth/login", json={"email": email, "password": pwd})
    if res.status_code == 200:
        data = res.json().get("data", {})
        tokens[role] = data.get("token")
        print(f"[{role.upper()}] SUCCESS | Name: {data.get('name')} | Role: {data.get('role')} | UserID: {data.get('id')}")
    else:
        print(f"[{role.upper()}] FAILED | Code: {res.status_code} | Msg: {res.text}")

print("\n=== 2. Testing Role Permissions & Dashboards ===")
headers_patient = {"Authorization": f"Bearer {tokens['patient']}"}
headers_coord = {"Authorization": f"Bearer {tokens['coordinator']}"}
headers_doc = {"Authorization": f"Bearer {tokens['doctor']}"}

# Patient dashboard projection
p_dash = requests.get(f"{base_url}/dashboards/patient", headers=headers_patient)
print(f"Patient Dashboard: {p_dash.status_code}")
if p_dash.status_code == 200:
    pd = p_dash.json().get("data", {})
    curr = pd.get("current_case", {})
    print(f"  Patient Case: {curr.get('case_number')} | Status: {curr.get('status')}")
    lc = pd.get("lifecycle", {})
    print(f"  Current Stage: {lc.get('current_stage_number')} ({lc.get('current_stage_id')})")

# Coordinator dashboard
c_dash = requests.get(f"{base_url}/dashboards/coordinator", headers=headers_coord)
print(f"Coordinator Dashboard: {c_dash.status_code}")
if c_dash.status_code == 200:
    cd = c_dash.json().get("data", {})
    print(f"  Coordinator Facility: {cd.get('facility')}")
    print(f"  Active Cases Count: {len(cd.get('cases', []))}")
    print(f"  Pending Tasks Count: {len(cd.get('tasks', []))}")

# Doctor dashboard
d_dash = requests.get(f"{base_url}/dashboards/doctor", headers=headers_doc)
print(f"Doctor Dashboard: {d_dash.status_code}")
if d_dash.status_code == 200:
    dd = d_dash.json().get("data", {})
    print(f"  Doctor Name: {dd.get('doctor_name')}")
    print(f"  Assigned Cases Count: {len(dd.get('cases', []))}")

print("\n=== 3. Testing Case Closure Permission Boundary ===")
# Coordinator attempts closure -> Must fail with 403 / Access Denied
close_attempt_coord = requests.post(
    f"{base_url}/cases/3cf166e5-4522-452f-a2f9-17f88877058b/clinical-closure",
    headers=headers_coord,
    json={"clinical_rationale": "Coordinator unauthorized attempt", "evidence_summary": "All tests done"}
)
print(f"Coordinator Close Attempt Status: {close_attempt_coord.status_code} (Expected 403: Forbidden)")
print(f"Coordinator Close Response: {close_attempt_coord.json().get('detail')}")

print("\n=== 4. Testing Outbox Health ===")
outbox_res = requests.get(f"{base_url}/health/outbox")
print(f"Outbox Health: {outbox_res.status_code} | Data: {outbox_res.json()}")
