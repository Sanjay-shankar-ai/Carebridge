import httpx

def test_live_endpoints():
    client = httpx.Client(base_url='http://127.0.0.1:8000', timeout=20.0)

    # 1. Doctor login
    doc_login = client.post('/api/v1/auth/login', json={'email': 'doctor@carebridge.com', 'password': 'DoctorPass123!'})
    assert doc_login.status_code == 200, doc_login.text
    doc_token = doc_login.json()['data']['token']
    doc_headers = {'Authorization': f'Bearer {doc_token}'}

    # 2. Doctor queries assignments
    assign_res = client.get('/api/v1/doctor/assignments', headers=doc_headers)
    assert assign_res.status_code == 200, assign_res.text
    assignments = assign_res.json()['data']
    print(f"Doctor assignments found: {len(assignments)}")

    # 3. Coordinator login
    coord_login = client.post('/api/v1/auth/login', json={'email': 'coordinator@carebridge.com', 'password': 'CoordinatorPass123!'})
    assert coord_login.status_code == 200, coord_login.text
    coord_token = coord_login.json()['data']['token']
    coord_headers = {'Authorization': f'Bearer {coord_token}'}

    # 4. Coordinator queries cases
    cases_res = client.get('/api/v1/cases', headers=coord_headers)
    cases = cases_res.json()['data']
    assert len(cases) > 0
    case_id = cases[0]['id']

    # 5. Coordinator queries ranked doctor candidates
    cand_res = client.get(f'/api/v1/cases/{case_id}/doctor-candidates', headers=coord_headers)
    assert cand_res.status_code == 200, cand_res.text
    candidates = cand_res.json()['data']
    print(f"Ranked candidates for case {case_id}: {len(candidates)}")
    for c in candidates[:3]:
        print(f"  - {c['name']} ({c['specialty']}) | Score: {c['total_score']} | Workload: {c['active_workload']}/{c['max_workload']}")

    print("\n>>> ALL LIVE REST DOCTOR ALLOCATION ENDPOINTS VERIFIED SUCCESSFULLY! <<<")

if __name__ == '__main__':
    test_live_endpoints()
