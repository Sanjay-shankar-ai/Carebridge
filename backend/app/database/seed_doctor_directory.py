import sys
import uuid
import os

sys.path.insert(0, os.path.abspath('backend'))
from app.database.session import get_sync_db
from app.models.owner import CaseOwner
from app.models.user import User
from app.core.security import hash_password

def seed():
    with get_sync_db() as db:
        # 1. Update existing specialists
        thorne = db.query(CaseOwner).filter(CaseOwner.name.like('%Thorne%')).first()
        if thorne:
            thorne.specialty = 'Breast Oncology'
            thorne.subspecialties = ['Breast Surgery', 'Diagnostic Biopsy', "Women's Specialty"]
            thorne.department = "Women's Health & Surgical Oncology"
            thorne.max_workload = 15
            thorne.eligibility_status = 'eligible'
            thorne.approved_case_categories = ['bi_rads_4', 'bi_rads_5', 'breast_mass', 'targeted_biopsy']
            thorne.working_hours = {'monday': ['09:00-17:00'], 'tuesday': ['09:00-17:00'], 'thursday': ['09:00-17:00']}

        chen = db.query(CaseOwner).filter(CaseOwner.name.like('%Chen%')).first()
        if chen:
            chen.specialty = 'Pulmonology'
            chen.subspecialties = ['Thoracic Oncology', 'Chest Imaging', 'Pulmonary Medicine']
            chen.department = 'Pulmonary & Respiratory Care'
            chen.max_workload = 15
            chen.eligibility_status = 'eligible'
            chen.approved_case_categories = ['lung_nodule', 'ldct_abnormal', 'chest_mass']
            chen.working_hours = {'monday': ['09:00-17:00'], 'wednesday': ['09:00-17:00'], 'friday': ['09:00-17:00']}

        rostova = db.query(CaseOwner).filter(CaseOwner.name.like('%Rostova%')).first()
        if rostova:
            rostova.specialty = 'Surgical Oncology'
            rostova.subspecialties = ['Colorectal Surgery', 'Gastrointestinal Oncology', 'General Surgery']
            rostova.department = 'Department of Surgery'
            rostova.max_workload = 15
            rostova.eligibility_status = 'eligible'
            rostova.approved_case_categories = ['colorectal_mass', 'fit_positive', 'biopsy_resection']
            rostova.working_hours = {'tuesday': ['09:00-17:00'], 'wednesday': ['09:00-17:00'], 'thursday': ['09:00-17:00']}

        sharma = db.query(CaseOwner).filter(CaseOwner.name.like('%Sharma%')).first()
        if sharma:
            sharma.specialty = 'Medical Oncology'
            sharma.subspecialties = ['Solid Tumors', 'Systemic Therapy', 'Clinical Oncology']
            sharma.department = 'Comprehensive Cancer Center'
            sharma.max_workload = 15
            sharma.eligibility_status = 'eligible'
            sharma.approved_case_categories = ['general_oncology', 'adjuvant_therapy']
            sharma.working_hours = {'monday': ['09:00-17:00'], 'thursday': ['09:00-17:00']}

        # 2. Add doctors for Dermatology, Cardiology, Orthopedics, Neurology
        additional_doctors = [
            {
                'name': 'Dr. Maya Lin, MD',
                'email': 'maya.lin@dermatology.org',
                'phone': '+91-98765-43220',
                'facility': 'Metropolitan Dermatology & Skin Cancer Center',
                'specialty': 'Dermatology',
                'subspecialties': ['Mohs Surgery', 'Cutaneous Oncology', 'Melanoma & Lesion Surveillance'],
                'department': 'Department of Dermatology',
                'approved_case_categories': ['skin_lesion', 'melanoma_suspicious', 'dysplastic_nevus'],
                'max_workload': 20,
            },
            {
                'name': 'Dr. Samuel Vance, MD',
                'email': 'samuel.vance@cardiology.org',
                'phone': '+91-98765-43221',
                'facility': 'Metropolitan Heart & Vascular Institute',
                'specialty': 'Cardiology',
                'subspecialties': ['Interventional Cardiology', 'Cardiovascular Imaging', 'Echocardiography'],
                'department': 'Department of Cardiology',
                'approved_case_categories': ['abnormal_ecg', 'troponin_elevated', 'coronary_eval', 'cardiac_biomarker'],
                'max_workload': 18,
            },
            {
                'name': 'Dr. David Kim, MD',
                'email': 'david.kim@orthopedics.org',
                'phone': '+91-98765-43222',
                'facility': 'Metropolitan Orthopedic & Joint Center',
                'specialty': 'Orthopedics',
                'subspecialties': ['Orthopedic Oncology', 'Musculoskeletal Imaging', 'Joint Reconstruction'],
                'department': 'Department of Orthopedic Surgery',
                'approved_case_categories': ['bone_lesion', 'joint_pathology', 'fracture_evaluation', 'musculoskeletal'],
                'max_workload': 20,
            },
            {
                'name': 'Dr. Sarah Patel, MD',
                'email': 'sarah.patel@neurology.org',
                'phone': '+91-98765-43223',
                'facility': 'Metropolitan Brain & Neuroscience Institute',
                'specialty': 'Neurology',
                'subspecialties': ['Neuro-Oncology', 'Epilepsy & EEG', 'Stroke & Neurovascular Care'],
                'department': 'Department of Neurology',
                'approved_case_categories': ['cranial_mri_abnormal', 'neuropathy', 'neurological_deficit', 'seizure'],
                'max_workload': 16,
            },
            # Inactive doctor for test verification (Criteria 4: Inactive doctor is never selected)
            {
                'name': 'Dr. Victor Stone, MD',
                'email': 'victor.stone@inactive.org',
                'phone': '+91-98765-43224',
                'facility': 'Metropolitan Dermatology & Skin Cancer Center',
                'specialty': 'Dermatology',
                'subspecialties': ['General Dermatology'],
                'department': 'Department of Dermatology',
                'approved_case_categories': ['skin_lesion'],
                'max_workload': 20,
                'is_active': False,
                'eligibility_status': 'suspended'
            }
        ]

        for doc_info in additional_doctors:
            existing = db.query(CaseOwner).filter(CaseOwner.email == doc_info['email']).first()
            if not existing:
                owner_id = uuid.uuid4()
                is_active = doc_info.get('is_active', True)
                owner = CaseOwner(
                    id=owner_id,
                    name=doc_info['name'],
                    role='specialist',
                    email=doc_info['email'],
                    phone=doc_info['phone'],
                    facility=doc_info['facility'],
                    is_active=is_active,
                    specialty=doc_info['specialty'],
                    subspecialties=doc_info['subspecialties'],
                    department=doc_info['department'],
                    max_workload=doc_info['max_workload'],
                    working_hours={'monday': ['09:00-17:00'], 'tuesday': ['09:00-17:00'], 'wednesday': ['09:00-17:00'], 'thursday': ['09:00-17:00'], 'friday': ['09:00-17:00']},
                    on_leave=False,
                    eligibility_status=doc_info.get('eligibility_status', 'eligible'),
                    approved_case_categories=doc_info['approved_case_categories'],
                    response_deadline_hours=24
                )
                db.add(owner)
                db.flush()

                # Create corresponding User account
                user = User(
                    id=uuid.uuid4(),
                    email=doc_info['email'],
                    password_hash=hash_password('DoctorPass123!'),
                    role='doctor',
                    full_name=doc_info['name'],
                    is_active=is_active,
                    is_verified=True,
                    owner_id=owner_id
                )
                db.add(user)
                print(f"Created specialist & user: {doc_info['name']} ({doc_info['specialty']}) active={is_active}")
            else:
                # Update attributes if needed
                existing.specialty = doc_info['specialty']
                existing.subspecialties = doc_info['subspecialties']
                existing.department = doc_info['department']
                existing.approved_case_categories = doc_info['approved_case_categories']
                existing.max_workload = doc_info['max_workload']

        db.commit()
        print("Specialist doctor directory successfully seeded!")

if __name__ == '__main__':
    seed()
