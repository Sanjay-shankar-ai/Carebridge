import sys, os
sys.path.insert(0, os.path.abspath("backend"))

import psycopg
from app.core.config import settings

conn = psycopg.connect(settings.CHECKPOINTER_DB_URI)
cur = conn.cursor()

print("=== 1. USERS TABLE DUMP ===")
cur.execute("SELECT id, email, role, full_name, is_active, is_verified, patient_id, owner_id FROM users ORDER BY role, email")
users = cur.fetchall()
for u in users:
    print(f"User ID: {u[0]} | Email: {u[1]} | Role: {u[2]} | Name: {u[3]} | Active: {u[4]} | Verified: {u[5]} | patient_id: {u[6]} | owner_id: {u[7]}")

print("\n=== 2. CASE OWNERS TABLE DUMP ===")
cur.execute("SELECT id, name, role, email, facility, is_active FROM case_owners")
owners = cur.fetchall()
for o in owners:
    print(f"Owner ID: {o[0]} | Name: {o[1]} | Role: {o[2]} | Email: {o[3]} | Facility: {o[4]} | Active: {o[5]}")

print("\n=== 3. FOREIGN KEY REFERENCES ACROSS DATABASE ===")
cur.execute("""
    SELECT
        tc.table_name, kcu.column_name, 
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name 
    FROM 
        information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
          AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.table_name;
""")
fks = cur.fetchall()
for fk in fks:
    print(f"{fk[0]}.{fk[1]} -> {fk[2]}.{fk[3]}")

print("\n=== 4. RECORD COUNTS LINKED TO USERS & OWNERS ===")
for u in users:
    uid, email, role, name, _, _, pid, oid = u
    print(f"\nAccount: {email} (Role: {role}, UID: {uid})")
    
    # Check audit_logs
    cur.execute("SELECT count(*) FROM audit_logs WHERE user_id = %s", (str(uid),))
    print(f"  - audit_logs (user_id): {cur.fetchone()[0]}")
    
    if oid:
        # Check care_cases owned
        cur.execute("SELECT count(*) FROM care_cases WHERE current_owner_id = %s", (oid,))
        print(f"  - care_cases (current_owner_id): {cur.fetchone()[0]}")
        # Check tasks assigned
        cur.execute("SELECT count(*) FROM tasks WHERE assigned_to_id = %s", (oid,))
        print(f"  - tasks (assigned_to_id): {cur.fetchone()[0]}")
        # Check closure_evidences verified
        cur.execute("SELECT count(*) FROM closure_evidences WHERE verifying_clinician_id = %s", (oid,))
        print(f"  - closure_evidences (verifying_clinician_id): {cur.fetchone()[0]}")
        # Check ownership history
        cur.execute("SELECT count(*) FROM case_ownership_history WHERE previous_owner_id = %s OR new_owner_id = %s", (oid, oid))
        print(f"  - case_ownership_history: {cur.fetchone()[0]}")
    else:
        print(f"  - No owner_id linked.")
        
    if pid:
        cur.execute("SELECT count(*) FROM care_cases WHERE patient_id = %s", (pid,))
        print(f"  - care_cases for patient: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM appointments WHERE patient_id = %s", (pid,))
        print(f"  - appointments for patient: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM communications WHERE patient_id = %s", (pid,))
        print(f"  - communications for patient: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM consents WHERE patient_id = %s", (pid,))
        print(f"  - consents for patient: {cur.fetchone()[0]}")
    else:
        print(f"  - No patient_id linked.")

conn.close()
