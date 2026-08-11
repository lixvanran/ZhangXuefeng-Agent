"""Prompt 模块 - 张雪峰风格 system prompt 拼装
模块结构:
- builder.py: build_system_prompt 入口
- style.py: 张雪峰风格 / 性格 / 边界
- fact_check.py: 事实校验规则
- scenarios/: 3 个场景独立文件 (volunteer / exam / chat)
- tools.py: tool schema 定义（暂放这里，Phase 1e 拆）
"""
from app.agent.prompts.builder import build_system_prompt
from app.agent.prompts.tools import TOOLS

__all__ = ["build_system_prompt", "TOOLS"]
