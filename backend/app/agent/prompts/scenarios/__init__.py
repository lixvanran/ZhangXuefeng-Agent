"""各场景 system prompt - 每个场景一个独立文件
- base.py: 默认场景 (chat)
- volunteer.py: 志愿填报
- exam.py: 备考
"""
from app.agent.prompts.scenarios import volunteer, exam, chat

SCENARIO_PROMPTS = {
    "volunteer": volunteer.PROMPT,
    "exam": exam.PROMPT,
    "chat": chat.PROMPT,
}
