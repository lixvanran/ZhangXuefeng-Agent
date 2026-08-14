"""Tool schema 定义 - 暴露给 LLM 的工具
暂放这里, Phase 1e 会拆到 tools/ 目录
"""
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_college",
            "description": "Find colleges based on score/rank/province. Returns 冲/稳/保 categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "score": {"type": "integer"},
                    "rank": {"type": "integer"},
                    "province": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["score", "province"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_major",
            "description": "Deep dive into a major: career, salary, traps, fit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "major_name": {"type": "string"},
                },
                "required": ["major_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_admission_probability",
            "description": "Estimate admission probability for a student at a college/major.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_rank": {"type": "integer"},
                    "college_name": {"type": "string"},
                    "major_name": {"type": "string"},
                    "year": {"type": "integer"},
                },
                "required": ["user_rank", "college_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "Search for the latest gaokao policies for a province.",
            "parameters": {
                "type": "object",
                "properties": {
                    "province": {"type": "string"},
                    "year": {"type": "integer"},
                    "keyword": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_match",
            "description": "按考生分数+省份+科类+策略(冲/稳/保)推荐匹配院校. 真实按省录取数据 + 估算兜底. 返回 top 10 院校及录取概率/位次/分数.",
            "parameters": {
                "type": "object",
                "properties": {
                    "score": {"type": "integer", "description": "考生分数 (0-750)"},
                    "province": {"type": "string", "description": "考生所在省份, 如 '山东' '河南' '江苏'"},
                    "subject_type": {"type": "string", "description": "科类, '物理类'/'历史类'/'理科'/'文科'/'综合'"},
                    "strategy": {"type": "string", "description": "填报策略: '冲'/'稳'/'保' (默认稳)"},
                    "limit": {"type": "integer", "description": "返回结果数 (默认 10)"},
                },
                "required": ["score", "province", "subject_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_schools",
            "description": "多院校综合对比. 输入学校名称列表, 返回每个学校的层次/城市/排名/王炸专业/张老师点评.",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_names": {"type": "array", "items": {"type": "string"}, "description": "学校名称列表, 如 ['北京大学','清华大学']"},
                    "dimensions": {"type": "array", "items": {"type": "string"}, "description": "对比维度 (可选), 如 ['tier','city','ranking','famous_majors']"},
                },
                "required": ["school_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "联网深度搜索 — 像豆包/Perplexity 一样: 搜多 provider + 抓全文 + 子问题拆解 + 整合。返回带全文摘录的搜索结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "返回条数 (默认 8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓单个 URL 全文 (给 search_web 后续用, 也能直接调)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "description": "最大字符数 (默认 6000)"},
                },
                "required": ["url"],
            },
        },
    },
    # ===== v0.8.0: workspace 文件夹操作 =====
    {
        "type": "function",
        "function": {
            "name": "workspace_info",
            "description": "看 workspace/ 整体信息 (在哪, 多少文件, 根目录列表)。给用户介绍 agent 能干啥时用, 或开始复杂任务前先看一眼。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": "列出 workspace/ 下文件/目录。支持 glob 模式 (如 '*.md', '错题本/*')",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径, 默认 '.' (workspace 根)"},
                    "pattern": {"type": "string", "description": "glob 模式, 默认 '*' = 全部"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read",
            "description": "读 workspace/ 下文件。自动跳过二进制, 大文件截断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径, 如 '笔记/数学.md'"},
                    "max_chars": {"type": "integer", "description": "最大字符 (默认 50000)"},
                    "start_line": {"type": "integer", "description": "从第 N 行开始读"},
                },
                "required": ["path"],
            },
        },
    },
    # v0.9.6: 加 read_file 工具 stub — LLM 经常幻觉调 read_file (训练数据里太常见)
    # 路由到 workspace_read, 兼容 LLM 的"自然"反应
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读 workspace/ 下的文件。**两阶段处理 uploads 错题**: 1) 先调 path='uploads' 列出待处理文件; 2) 再对每个文件调 path='uploads/xxx.jpg', 图片会自动用 Vision 识别错题内容。等效 workspace_read, 是 LLM 容易想到的通用别名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径。传 'uploads' 列出待处理文件, 传 'uploads/photo1.jpg' 读取并识别该图片, 传 '笔记/数学.md' 读文本文件"},
                    "max_chars": {"type": "integer", "description": "最大字符 (默认 50000)"},
                    "start_line": {"type": "integer", "description": "从第 N 行开始读"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write",
            "description": "写 workspace/ 下文件。自动创建父目录。mode=overwrite 覆盖, append 追加。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径, 如 '错题本/圆.md'"},
                    "content": {"type": "string", "description": "完整文件内容"},
                    "mode": {"type": "string", "description": "'overwrite' 或 'append', 默认 overwrite"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_search",
            "description": "在 workspace/ 下搜文件内容 (中文友好)。返回匹配行+文件名+行号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "description": "搜索根目录, 默认 '.' = 全部"},
                    "max_results": {"type": "integer", "description": "默认 20"},
                    "file_pattern": {"type": "string", "description": "文件名 glob, 默认 '*'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_delete",
            "description": "删除 workspace/ 下文件或空目录 (安全, 不递归删非空目录)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    # ===== v0.9.1 错题本工具 =====
    {
        "type": "function",
        "function": {
            "name": "wrong_book_scan_uploads",
            "description": "扫描 workspace/uploads/ 目录, 列出所有待处理文件 (用户从桌面拖进来的错题图片/PDF/Word 等)。当用户说'把上传文件夹里的错题整理一下'或'看看上传文件夹里有什么'时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wrong_book_describe_file",
            "description": "用 Vision 模型识别 uploads/ 里某个图片/PDF/文本文件的内容, 提取错题原文。识别后再用 wrong_book_add_mistake 写入错题本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "uploads/ 下的文件名, 如 'uploads/photo1.jpg'",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wrong_book_add_mistake",
            "description": "把识别出的内容写入错题本。自动生成错题编号 (M-001, M-002...) 并加入 RAG 索引, 后续 Agent 可以引用。**v0.9.6 重要**: file_path 必传 (来自 wrong_book_describe_file 的返回值, 如 'uploads/photo1.jpg'), 不传则错题本里看不到原图。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "错题标题, 简短描述, 如 '圆锥曲线离心率'"},
                    "content": {"type": "string", "description": "错题内容/题目原文"},
                    "file_path": {"type": "string", "description": "**必传**: 关联的文件路径, 来自 wrong_book_describe_file 的返回值, 如 'uploads/photo1.jpg'"},
                    "subject": {"type": "string", "description": "学科, 如 '数学'/'语文'/'英语'/'物理'/'化学'/'生物'/'历史'/'地理'/'政治'"},
                    "knowledge_point": {"type": "string", "description": "知识点, 如 '圆锥曲线'/'函数'"},
                    "error_type": {"type": "string", "description": "错误类型, 如 '计算错误'/'概念不清'/'方法不会'/'审题错误'"},
                    "notes": {"type": "string", "description": "备注 (可选)"},
                },
                "required": ["title", "content", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wrong_book_query",
            "description": "查询错题本。按学科/知识点/掌握状态过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "按学科过滤, 如 '数学'"},
                    "knowledge_point": {"type": "string", "description": "按知识点模糊匹配"},
                    "mastered": {"type": "boolean", "description": "是否已掌握"},
                    "limit": {"type": "integer", "description": "返回数量, 默认 20"},
                },
            },
        },
    },
]
