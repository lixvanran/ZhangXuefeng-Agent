"""Service 层 - 业务逻辑
- chat_service: 聊天的业务编排
- conversation_service: 会话管理
- user_service: 用户/画像
- tts_service: 语音合成
- resource_service: 资料管理 (已有, 保留)

设计原则: routers 只做参数解析 + 调 service
"""
