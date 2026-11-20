import sys
sys.path.insert(0, 'backend')
from app.services.llm_service import llm_service
from app.core.config import settings
from langchain_groq import ChatGroq
from app.agents.cognitive_engine import INTENT_ANALYSIS_PROMPT, intent_parser, PLANNING_PROMPT, plan_parser
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.prompts import CAREBRIDGE_SYSTEM_PROMPT

primary = ChatGroq(model="openai/gpt-oss-120b", api_key=settings.GROQ_API_KEY, temperature=0.1, timeout=10.0, max_retries=1)
fallback = ChatGroq(model="openai/gpt-oss-20b", api_key=settings.GROQ_API_KEY, temperature=0.1, timeout=10.0, max_retries=1)
llm = primary.with_fallbacks([fallback])

# Test 1: Greeting
prompt1 = f"{INTENT_ANALYSIS_PROMPT.format(message='Hello, how are you?', preferred_language='en', case_summary='Mammogram - BI-RADS 4')}\n\n{intent_parser.get_format_instructions()}"
res1 = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt1)])
parsed1 = intent_parser.parse(res1.content)
print("Test 1 - Greeting Intent:", parsed1.primary_intent)

# Test 2: Screening inquiry
prompt2 = f"{INTENT_ANALYSIS_PROMPT.format(message='What does BI-RADS 4 mean? Am I going to be okay?', preferred_language='en', case_summary='Mammogram - BI-RADS 4')}\n\n{intent_parser.get_format_instructions()}"
res2 = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt2)])
parsed2 = intent_parser.parse(res2.content)
print("Test 2 - Screening Inquiry Intent:", parsed2.primary_intent, "| emotional:", parsed2.emotional_state, "| barriers:", [b.barrier_type for b in parsed2.detected_barriers])

# Test 3: Acute symptom
prompt3 = f"{INTENT_ANALYSIS_PROMPT.format(message='I have severe bleeding and acute chest pain right now', preferred_language='en', case_summary='Mammogram - BI-RADS 4')}\n\n{intent_parser.get_format_instructions()}"
res3 = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt3)])
parsed3 = intent_parser.parse(res3.content)
print("Test 3 - Acute Symptom Intent:", parsed3.primary_intent, "| escalation:", parsed3.requires_human_escalation)
