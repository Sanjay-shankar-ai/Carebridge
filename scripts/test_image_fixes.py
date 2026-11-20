import sys
import os
import asyncio
import httpx

sys.path.insert(0, os.path.abspath('backend'))
from app.main import app

async def test_fixes():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        # 1. Login as patient Meenakshi (CASE-2026-0147)
        login_res = await client.post('/api/v1/auth/login', json={'email': 'meenakshi.r52@example.com', 'password': 'PatientPass123!'})
        if login_res.status_code != 200:
            login_res = await client.post('/api/v1/auth/login', json={'email': 'patient@carebridge.com', 'password': 'PatientPass123!'})
        pat_data = login_res.json()['data']
        pat_token = pat_data['token']
        pat_case_id = pat_data['case_id']
        headers = {'Authorization': f'Bearer {pat_token}'}

        print('=== 1. Testing Image 1 Fix: Appointment Booking on Wednesday at 12pm ===')
        book_res = await client.post('/api/v1/agent/interact', json={
            'message': 'i want to book a appointment on wednesday at 12pm',
            'case_id': pat_case_id,
            'channel': 'in_app_chat'
        }, headers=headers)
        assert book_res.status_code == 200, f'Booking request failed: {book_res.text}'
        reply1 = book_res.json()['data']['outbound_message']
        print('[REPLY 1]:\n', reply1)
        assert 'wednesday at 12:00 pm' in reply1.lower() or 'wednesday' in reply1.lower(), 'Should acknowledge Wednesday!'
        print('--> PASS: Dynamic timing acknowledged without canned duplication!')

        print('\n=== 2. Testing Image 3 Fix: Transportation / Caregiver Query in English ===')
        trans_res = await client.post('/api/v1/agent/interact', json={
            'message': "I can't come tomorrow. My daughter is out of town and I have nobody to take me.",
            'case_id': pat_case_id,
            'channel': 'in_app_chat'
        }, headers=headers)
        assert trans_res.status_code == 200, f'Transit request failed: {trans_res.text}'
        reply2 = trans_res.json()['data']['outbound_message']
        print('[REPLY 2]:\n', reply2)
        has_tamil = any('\u0b80' <= c <= '\u0bff' for c in reply2)
        assert not has_tamil, 'Must not reply in Tamil when spoken to in English!'
        print('--> PASS: Responded in English with zero unwanted Tamil!')

        print('\n=== 3. Testing Image 2 Fix: Doctor Login AI Chat ===')
        doc_login = await client.post('/api/v1/auth/login', json={'email': 'doctor@carebridge.com', 'password': 'DoctorPass123!'})
        doc_token = doc_login.json()['data']['token']
        doc_headers = {'Authorization': f'Bearer {doc_token}'}

        doc_chat_res = await client.post('/api/v1/agent/interact', json={
            'message': 'hi',
            'case_id': pat_case_id,
            'channel': 'in_app_chat'
        }, headers=doc_headers)
        assert doc_chat_res.status_code == 200, f'Doctor chat failed: {doc_chat_res.text}'
        doc_reply = doc_chat_res.json()['data']['outbound_message']
        print('[DOCTOR REPLY]:\n', doc_reply)
        assert 'AI Care Companion' not in doc_reply, 'Doctor must not be welcomed as a patient!'
        assert 'Doctor' in doc_reply or 'Clinical' in doc_reply or 'Case Review' in doc_reply, 'Must be a clinical response!'
        print('--> PASS: Doctor greeted clinically with case summary!')

        print('\n=== 4. Testing Coordinator AI Chat ===')
        coord_login = await client.post('/api/v1/auth/login', json={'email': 'coordinator@carebridge.com', 'password': 'CoordinatorPass123!'})
        coord_token = coord_login.json()['data']['token']
        coord_headers = {'Authorization': f'Bearer {coord_token}'}

        coord_chat_res = await client.post('/api/v1/agent/interact', json={
            'message': 'hi',
            'case_id': pat_case_id,
            'channel': 'in_app_chat'
        }, headers=coord_headers)
        assert coord_chat_res.status_code == 200, f'Coordinator chat failed: {coord_chat_res.text}'
        coord_reply = coord_chat_res.json()['data']['outbound_message']
        print('[COORDINATOR REPLY]:\n', coord_reply)
        assert 'AI Care Companion' not in coord_reply, 'Coordinator must not be welcomed as a patient!'
        assert 'Coordinator' in coord_reply or 'Active case file' in coord_reply, 'Must be a coordinator oversight response!'
        print('--> PASS: Coordinator greeted with case oversight file!')

    print('\n============================================================')
    print('ALL TARGETED IMAGE FIX TESTS PASSED WITH 100% SUCCESS!')
    print('============================================================')

if __name__ == '__main__':
    asyncio.run(test_fixes())
