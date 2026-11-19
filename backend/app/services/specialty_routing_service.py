"""
CareBridge Clinical Specialty Routing Service
Determines the appropriate medical specialty based on documented screening findings,
organ systems, ICD/LOINC concepts, and clinical urgency.
Configurable and rule-governed — never guesses or independently diagnoses diseases.
If findings are ambiguous or confidence is low, requires human clinical review.
"""

import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class SpecialtyRoutingResult(BaseModel):
    specialty: Optional[str] = None
    subspecialties: List[str] = []
    confidence: float = 0.0
    urgency_level: str = "standard"  # "standard", "urgent", "critical"
    supporting_evidence: List[str] = []
    requires_human_review: bool = False
    routing_rationale: str = ""
    suggested_department: Optional[str] = None


# Clinically approved specialty routing matrices
SPECIALTY_RULE_REGISTRY: List[Dict[str, Any]] = [
    {
        "specialty": "Dermatology",
        "department": "Department of Dermatology",
        "subspecialties": ["Mohs Surgery", "Cutaneous Oncology", "Melanoma & Lesion Surveillance"],
        "keywords": [
            "skin", "lesion", "melanoma", "nevus", "dysplastic", "dermatology",
            "mole", "rash", "epidermal", "squamous cell", "basal cell", "cutaneous"
        ],
        "category_codes": ["SKIN", "DERM", "MELANOMA", "CUTANEOUS"]
    },
    {
        "specialty": "Cardiology",
        "department": "Department of Cardiology",
        "subspecialties": ["Interventional Cardiology", "Cardiovascular Imaging", "Echocardiography"],
        "keywords": [
            "heart", "cardiac", "cardiology", "ecg", "ekg", "troponin", "arrhythmia",
            "coronary", "myocardial", "echocardiogram", "ejection fraction", "cardiovascular"
        ],
        "category_codes": ["CARD", "ECG", "TROPONIN", "CARDIAC"]
    },
    {
        "specialty": "Orthopedics",
        "department": "Department of Orthopedic Surgery",
        "subspecialties": ["Orthopedic Oncology", "Musculoskeletal Imaging", "Joint Reconstruction"],
        "keywords": [
            "bone", "joint", "orthopedic", "fracture", "musculoskeletal", "arthropathy",
            "spine", "femur", "tibia", "cartilage", "osteolytic", "tendon", "ligament"
        ],
        "category_codes": ["ORTHO", "BONE", "JOINT", "FRACTURE"]
    },
    {
        "specialty": "Neurology",
        "department": "Department of Neurology",
        "subspecialties": ["Neuro-Oncology", "Epilepsy & EEG", "Stroke & Neurovascular Care"],
        "keywords": [
            "brain", "neurology", "neurological", "seizure", "eeg", "cranial", "stroke",
            "neuropathy", "headache", "intracranial", "motor deficit", "parasthesia"
        ],
        "category_codes": ["NEURO", "BRAIN", "EEG", "SEIZURE"]
    },
    {
        "specialty": "Breast Oncology",
        "department": "Women's Health & Surgical Oncology",
        "subspecialties": ["Breast Surgery", "Diagnostic Biopsy", "Women's Specialty"],
        "keywords": [
            "breast", "mammogram", "mammography", "bi-rads", "ductal", "calcification",
            "microcalcifications", "lumpectomy", "dense breast tissue", "nipple discharge"
        ],
        "category_codes": ["BI-RADS", "BI_RADS", "MAMMOGRAM", "BREAST"]
    },
    {
        "specialty": "Pulmonology",
        "department": "Pulmonary & Respiratory Care",
        "subspecialties": ["Thoracic Oncology", "Chest Imaging", "Pulmonary Medicine"],
        "keywords": [
            "lung", "pulmonary", "respiratory", "ldct", "chest ct", "bronchoscopy",
            "pleural", "atelectasis", "spiculation", "pulmonology", "trachea"
        ],
        "category_codes": ["LDCT", "LUNG", "PULMONARY", "CHEST_CT"]
    },
    {
        "specialty": "Surgical Oncology",
        "department": "Department of Surgery",
        "subspecialties": ["Colorectal Surgery", "Gastrointestinal Oncology", "General Surgery"],
        "keywords": [
            "colon", "colorectal", "fit-positive", "fit positive", "colonoscopy",
            "polyp", "adenocarcinoma", "bowel", "resection", "gi tract"
        ],
        "category_codes": ["FIT", "COLON", "COLORECTAL", "GI"]
    },
    {
        "specialty": "Medical Oncology",
        "department": "Comprehensive Cancer Center",
        "subspecialties": ["Solid Tumors", "Systemic Therapy", "Clinical Oncology"],
        "keywords": [
            "oncology", "neoplasm", "metastasis", "systemic therapy", "solid tumor",
            "carcinoma", "adjuvant", "immunotherapy", "biomarker"
        ],
        "category_codes": ["ONCOLOGY", "NEOPLASM", "TUMOR"]
    }
]


class SpecialtyRoutingService:
    """Evaluates screening finding records to determine required medical specialty."""

    @classmethod
    def determine_specialty(
        cls,
        disease_condition: Optional[str] = None,
        finding_code: Optional[str] = None,
        finding_summary: Optional[str] = None,
        screening_type: Optional[str] = None,
        report_text: Optional[str] = None,
        urgency_level: Optional[str] = None
    ) -> SpecialtyRoutingResult:
        """
        Determines the clinical specialty using approved clinical routing rules.
        If confidence is < 0.75 or findings are ambiguous, sets requires_human_review=True.
        """
        corpus_parts = [
            disease_condition or "",
            finding_code or "",
            finding_summary or "",
            screening_type or "",
            report_text or ""
        ]
        corpus = " ".join(corpus_parts).lower().strip()

        if not corpus or len(corpus) < 4:
            return SpecialtyRoutingResult(
                specialty=None,
                confidence=0.0,
                urgency_level=urgency_level or "standard",
                supporting_evidence=[],
                requires_human_review=True,
                routing_rationale="Insufficient clinical text provided to determine specialty. Escalate to coordinator for human review."
            )

        # Check for vague/inconclusive patterns that mandate human review
        vague_patterns = [
            "unspecified malaise", "inconclusive", "unclear findings", "indeterminate",
            "non-specific", "cannot determine", "general checkup without findings"
        ]
        if any(v in corpus for v in vague_patterns) and not any(k in corpus for k in ["bi-rads-4", "bi-rads-5", "melanoma", "fracture", "infarct"]):
            return SpecialtyRoutingResult(
                specialty=None,
                confidence=0.2,
                urgency_level=urgency_level or "standard",
                supporting_evidence=["Report explicitly documents non-specific or indeterminate findings."],
                requires_human_review=True,
                routing_rationale="Clinical findings are indeterminate or non-specific. Human review by coordinator or attending physician is required."
            )

        scored_matches = []
        for rule in SPECIALTY_RULE_REGISTRY:
            matched_terms = []
            score = 0.0

            # 1. Exact category code match
            for code in rule.get("category_codes", []):
                if code.lower() in (finding_code or "").lower() or code.lower() in (screening_type or "").lower():
                    score += 0.45
                    matched_terms.append(f"category_code:{code}")

            # 2. Keyword occurrences
            for kw in rule.get("keywords", []):
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, corpus):
                    score += 0.20
                    matched_terms.append(kw)

            if score > 0:
                normalized_score = min(score, 1.0)
                scored_matches.append({
                    "specialty": rule["specialty"],
                    "department": rule["department"],
                    "subspecialties": rule["subspecialties"],
                    "confidence": normalized_score,
                    "matched_terms": matched_terms
                })

        if not scored_matches:
            return SpecialtyRoutingResult(
                specialty=None,
                confidence=0.0,
                urgency_level=urgency_level or "standard",
                supporting_evidence=[],
                requires_human_review=True,
                routing_rationale="No approved clinical routing rules matched the reported findings. Requires human clinical review."
            )

        scored_matches.sort(key=lambda x: x["confidence"], reverse=True)
        top = scored_matches[0]

        # Check for ambiguity (e.g. 2 different specialties with identical close scores)
        if len(scored_matches) > 1 and (top["confidence"] - scored_matches[1]["confidence"] < 0.10) and top["confidence"] < 0.70:
            return SpecialtyRoutingResult(
                specialty=None,
                confidence=top["confidence"],
                urgency_level=urgency_level or "standard",
                supporting_evidence=top["matched_terms"],
                requires_human_review=True,
                routing_rationale=f"Ambiguous clinical routing between {top['specialty']} and {scored_matches[1]['specialty']}. Coordinator review required."
            )

        # Minimum confidence threshold (0.60) for automated allocation
        if top["confidence"] < 0.60:
            return SpecialtyRoutingResult(
                specialty=None,
                confidence=top["confidence"],
                urgency_level=urgency_level or "standard",
                supporting_evidence=top["matched_terms"],
                requires_human_review=True,
                routing_rationale=f"Confidence ({round(top['confidence'], 2)}) below clinical threshold (0.60). Human review required."
            )

        # Calculate clinical urgency
        inferred_urgency = urgency_level or "standard"
        if any(k in corpus for k in ["bi-rads 5", "bi-rads-5", "critical", "acute", "malignancy", "occlusion", "severe", "fracture displaced", "st elevation", "infarct"]):
            inferred_urgency = "critical"
        elif any(k in corpus for k in ["bi-rads 4", "bi-rads-4", "urgent", "suspicious", "positive", "nodule", "dysplastic", "troponin", "elevated", "elevation"]):
            if inferred_urgency != "critical":
                inferred_urgency = "urgent"

        return SpecialtyRoutingResult(
            specialty=top["specialty"],
            subspecialties=top["subspecialties"],
            suggested_department=top["department"],
            confidence=round(top["confidence"], 2),
            urgency_level=inferred_urgency,
            supporting_evidence=top["matched_terms"],
            requires_human_review=False,
            routing_rationale=f"Matched clinical specialty '{top['specialty']}' via evidence: {', '.join(top['matched_terms'][:4])}."
        )
