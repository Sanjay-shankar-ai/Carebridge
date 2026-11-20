import requests, json

res = requests.post('http://localhost:8000/api/v1/auth/login', json={'email': 'patient@carebridge.com', 'password': 'PatientPass123!'})
token = res.json()['data']['token']

p = requests.get('http://localhost:8000/api/v1/dashboards/patient', headers={'Authorization': f'Bearer {token}'})
data = p.json()['data']
lc = data.get('lifecycle', {})
print('Total stages:', len(lc.get('stages', [])))
for s in lc.get('stages', []):
    sn = s.get('stage_number')
    sid = s.get('stage_id')
    st = s.get('status')
    print(f"  Stage {sn}: {sid} | {st}")
print('Case:', data.get('current_case', {}).get('case_number'), data.get('current_case', {}).get('status'))
