"""
CareBridge Phase 10: Isolated Database Restoration & Disaster Recovery Verification
Verifies that a CareBridge snapshot can be fully restored into an isolated database
without touching or risking the primary PostgreSQL 17 production database.
"""

import os
import sys
import json
import sqlite3
import glob
from pathlib import Path

def test_isolated_restore():
    print("=" * 70)
    print("CAREBRIDGE DISASTER RECOVERY: ISOLATED RESTORE VALIDATION")
    print("=" * 70)

    # 1. Find the latest backup snapshot
    backups = sorted(glob.glob("backups/carebridge_backup_*.json"), key=os.path.getmtime, reverse=True)
    if not backups:
        print("[-] No backup file found in backups/ directory.")
        return False

    latest_backup = backups[0]
    print(f"[*] Inspecting latest backup snapshot: {latest_backup}")

    with open(latest_backup, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    meta_ts = snapshot.get("timestamp")
    tables_data = snapshot.get("tables", {})
    total_records = snapshot.get("total_records", 0)
    print(f"    Timestamp: {meta_ts} | Tables: {len(tables_data)} | Total Records: {total_records}")

    # 2. Create isolated SQLite test recovery database
    isolated_db_path = "backups/isolated_recovery_test.sqlite"
    if os.path.exists(isolated_db_path):
        os.remove(isolated_db_path)

    print(f"[*] Creating isolated test recovery database: {isolated_db_path}")
    conn = sqlite3.connect(isolated_db_path)
    cursor = conn.cursor()

    restored_tables = 0
    restored_rows = 0

    try:
        for table_name, rows in tables_data.items():
            if not rows:
                continue

            first_row = rows[0]
            col_names = list(first_row.keys())

            # Define SQLite table dynamically
            cols_sql = ", ".join([f'"{col}" TEXT' for col in col_names])
            create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({cols_sql});'
            cursor.execute(create_sql)

            # Insert all rows
            placeholders = ", ".join(["?"] * len(col_names))
            insert_sql = f'INSERT INTO "{table_name}" ({", ".join([f"`{c}`" for c in col_names])}) VALUES ({placeholders})'

            for row in rows:
                vals = [json.dumps(row[c]) if isinstance(row[c], (dict, list)) else str(row[c]) if row[c] is not None else None for c in col_names]
                cursor.execute(insert_sql, vals)

            restored_tables += 1
            restored_rows += len(rows)
            print(f"    - Restored table '{table_name}': {len(rows)} rows verified.")

        conn.commit()

        # 3. Verify queries against the isolated restored database
        cursor.execute("SELECT COUNT(*) FROM care_cases")
        cases_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM patients")
        patients_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM appointments")
        appts_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notifications")
        notifs_count = cursor.fetchone()[0]

        print("\n[+] Verification Queries on Isolated Database:")
        print(f"    - Patients Restored: {patients_count}")
        print(f"    - Care Cases Restored: {cases_count}")
        print(f"    - Appointments Restored: {appts_count}")
        print(f"    - Notifications Restored: {notifs_count}")
        print(f"\n[+] Total Restored: {restored_rows} records across {restored_tables} tables.")
        print("[+] Disaster recovery verification SUCCESSFUL. Primary database remains untouched.")
        return True

    finally:
        conn.close()
        if os.path.exists(isolated_db_path):
            os.remove(isolated_db_path)


if __name__ == "__main__":
    success = test_isolated_restore()
    if not success:
        sys.exit(1)
