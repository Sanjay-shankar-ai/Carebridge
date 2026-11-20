import sys
sys.path.insert(0, 'backend')
from langchain_groq import ChatGroq
from app.core.config import settings
from app.agents.cognitive_engine import PLANNING_PROMPT, plan_parser
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.prompts import CAREBRIDGE_SYSTEM_PROMPT

llm = ChatGroq(model='openai/gpt-oss-20b', api_key=settings.GROQ_API_KEY, temperature=0.1)
prompt = (
    f"{PLANNING_PROMPT.format(case_number='CASE-2026-0001', patient_name='Meenakshi Ramanathan', language='en', case_status='active', screening_finding='BI-RADS 4: Suspicious finding', sla_status='normal', sla_deadline='in 7 days', situation_summary='Intent: greeting. Emotional state: cooperative. Barriers: []')}\n\n"
    f"{plan_parser.get_format_instructions()}"
)
res = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)])
print('LLM Response:\n', res.content)
parsed = plan_parser.parse(res.content)
print('Parsed goal:', parsed.goal)
print('Parsed draft:', parsed.patient_response_draft)
