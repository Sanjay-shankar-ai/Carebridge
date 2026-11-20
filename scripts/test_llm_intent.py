import sys
sys.path.insert(0, 'backend')
from langchain_groq import ChatGroq
from app.core.config import settings
from app.agents.cognitive_engine import INTENT_ANALYSIS_PROMPT, intent_parser
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.prompts import CAREBRIDGE_SYSTEM_PROMPT

llm = ChatGroq(model='openai/gpt-oss-20b', api_key=settings.GROQ_API_KEY, temperature=0.1)
prompt = (
    f"{INTENT_ANALYSIS_PROMPT.format(message='Hello', preferred_language='en', case_summary='Mammogram - BI-RADS 4')}\n\n"
    f"{intent_parser.get_format_instructions()}"
)
res = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)])
print('LLM Response:\n', res.content)
parsed = intent_parser.parse(res.content)
print('Parsed intent:', parsed.primary_intent, '| emotional:', parsed.emotional_state)
