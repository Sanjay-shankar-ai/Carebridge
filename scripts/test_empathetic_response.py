import sys
sys.path.insert(0, 'backend')
from app.services.llm_service import llm_service
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.prompts import CAREBRIDGE_SYSTEM_PROMPT

llm = llm_service.get_llm()

prompt = """
The patient Meenakshi Ramanathan says: "I'm really scared about this. What should I do?"
Context:
- Screening: Mammogram
- Finding: BI-RADS 4 (Suspicious finding requiring tissue biopsy)
- Previous turn: Assistant explained that BI-RADS 4 requires further evaluation.

Generate an empathetic, comforting, factual response for Meenakshi.
Rules:
- Acknowledge and validate her fear with deep empathy.
- Reassure her that 70-80% of BI-RADS 4 biopsies turn out completely benign.
- Strictly DO NOT diagnose or prescribe.
- Offer clear, supportive next steps and ask a relevant follow-up question.
- Keep it concise (3-4 sentences).
"""

res = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)])
print("LLM Empathetic Response:\n", res.content)
