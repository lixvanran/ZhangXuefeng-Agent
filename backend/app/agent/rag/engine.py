"""RAG 引擎 - 入口 ZhangRAG
组合 tokenizer / indexer / ranker / boost, 提供对外 API
"""
import json
import logging
import re as _re
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.core.config import settings
from app.agent.rag.tokenizer import tokenize
from app.agent.rag.indexer import EmbeddingService
from app.agent.rag.ranker import cosine, keyword_score
from app.agent.rag.boost import maybe_apply_boost
from app.agent.rag.kb_registry import KBRegistry

logger = logging.getLogger(__name__)


# 知识库每类 item 的"索引文本"提取规则
# v0.8.0: 重做后的 KB 文件名 + 字段, 替代旧的 admission/career/cities/colleges/life_kb/majors/policy/strategy/zhang_quotes/zhang_strategy_2026
KB_INDEX_FIELD = {
    # ===== v0.8.0 新 KB schema =====
    "01_persona": lambda item: f"{item.get('name', '')} {item.get('type', '')} {item.get('core', '')} {item.get('summary', '')} {' '.join(item.get('tags', []))}",
    "02_quotes": lambda item: f"{item.get('category', '')} {item.get('text', '')} {item.get('context', '')} {' '.join(item.get('tags', []))}",
    "03_majors": lambda item: f"{item.get('name', '')} {item.get('category_zh', '')} {item.get('sub_category', '')} {item.get('comment', '')} {item.get('warning', '')} {item.get('tags', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    "04_universities": lambda item: f"{item.get('name', '')} {item.get('city', '')} {item.get('tier', '')} {item.get('features', '')} {' '.join(item.get('famous_majors', []))} {item.get('zxf_comment', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    "05_volunteer_strategy": lambda item: f"{item.get('text', '')} {item.get('name', '')} {item.get('content', '')} {item.get('context', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    "06_career_employment": lambda item: f"{item.get('text', '')} {item.get('title', '')} {item.get('content', '')} {item.get('context', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    "07_life_study": lambda item: f"{item.get('text', '')} {item.get('title', '')} {item.get('content', '')} {item.get('context', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    # ===== v0.8.0: 借鉴参考项目新增的 2 个 KB =====
    "08_admission_scores": lambda item: f"{item.get('school_name', '')} {item.get('province', '')} {item.get('subject_type', '')} {item.get('batch', '')} {item.get('min_score', '')} {item.get('min_rank', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    "09_policies": lambda item: f"{item.get('name', '')} {item.get('type', '')} {item.get('summary', '')} {' '.join(item.get('key_points', []))} {item.get('scope', '')} {item.get('zxf_comment', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
    # ===== v0.9.8: 集成 2 个开源 KB (CC BY 4.0 + MIT, 124 篇高质量内容) =====
    "10_external_kb": lambda item: f"{item.get('text', '')} {item.get('context', '')} {' '.join(item.get('tags', []) if isinstance(item.get('tags'), list) else [])}",
}


# 知识库每类 item 的"展示文本"提取规则
KB_DISPLAY_FIELD = {
    "01_persona": lambda item: f"[{item.get('type', 'persona')}] {item.get('name', '')}" + (f"\n核心: {item.get('core', '')}" if item.get('core') else f"\n{item.get('summary', '')[:200]}"),
    "02_quotes": lambda item: f"[{item.get('category', '语录')}] \"{item.get('text', '')}\"\n场景: {item.get('context', '')}",
    "03_majors": lambda item: f"专业: {item.get('name')} ({item.get('category_zh', '')})\n就业率: {item.get('employment_rate', '?')} | 月薪: {item.get('median_salary', '?')} | 考研: {item.get('grad_school_ratio', '?')}\n张老师点评: {item.get('comment', '')}",
    "04_universities": lambda item: f"院校: {item.get('name')} ({item.get('tier', '')})\n城市: {item.get('city')} | 最低分(2024): {item.get('min_score_2024', '?')} | 位次: {item.get('min_rank_2024', '?')}\n特色: {item.get('features', '')}\n王炸专业: {', '.join(item.get('famous_majors', []))}\n张老师点评: {item.get('zxf_comment', '')}",
    "05_volunteer_strategy": lambda item: f"[{item.get('type', '策略')}] {item.get('name') or item.get('text', '')[:50]}\n{item.get('content') or item.get('text', '')}",
    "06_career_employment": lambda item: f"[{item.get('type', '就业')}] {item.get('title') or item.get('text', '')[:50]}\n{item.get('content') or item.get('text', '')}",
    "07_life_study": lambda item: f"[{item.get('category') or item.get('type', '人生')}] {item.get('title') or item.get('text', '')[:50]}\n{item.get('content') or item.get('text', '')}",
    "08_admission_scores": lambda item: f"录取数据: {item.get('school_name')} {item.get('province')} {item.get('subject_type', '')} {item.get('year')}年\n最低分: {item.get('min_score', '?')} | 平均分: {item.get('avg_score', '?')} | 最高分: {item.get('max_score', '?')} | 最低位次: {item.get('min_rank', '?')}",
    "09_policies": lambda item: f"[{item.get('type', '政策')}] {item.get('name')}\n{item.get('summary', '')}\n要点: {'; '.join(item.get('key_points', [])[:3])}\n张老师点评: {item.get('zxf_comment', '')}",
    "10_external_kb": lambda item: f"[{item.get('topic', '外部KB')}] {item.get('context', '')[:80]}\n{item.get('text', '')}" + (f"\n[来源: {item.get('source', '?')} / {item.get('license', '?')}]" if item.get('source') else ""),
}


# v0.10.0: 原有 10 个库的 schema 打包成 (index_fn, display_fn)。
# 新增知识库不再需要往上面两个 dict 里加条目 —— 走 KBRegistry 的通用兜底即可;
# 只有需要特殊展示格式时才在 _load_kb() 里显式覆盖。
_LEGACY_KB_SCHEMAS = {
    name: (KB_INDEX_FIELD[name], KB_DISPLAY_FIELD[name])
    for name in KB_INDEX_FIELD
    if name in KB_DISPLAY_FIELD
}


def _first_meta(items: list, key: str) -> str:
    """从条目里取第一个非空的 source/license, 作为整个库的元数据"""
    for it in items[:20]:
        if isinstance(it, dict) and it.get(key):
            return str(it[key])
    return ""


class ZhangRAG:
    """In-memory RAG with persistent JSON storage"""

    def __init__(self):
        self.embedding = EmbeddingService()
        self.knowledge_base = self._load_kb()
        self.store_path = settings.CHROMA_DIR / "user_index.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_index: Dict[str, Dict[str, Dict]] = self._load_user_index()
        logger.info(f"RAG initialized: {len(self.user_index)} users indexed")

    # ========== 加载/持久化 ==========

    def _load_user_index(self) -> Dict:
        if self.store_path.exists():
            try:
                return json.loads(self.store_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load user index: {e}")
        return {}

    def _save_user_index(self):
        try:
            self.store_path.write_text(
                json.dumps(self.user_index, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save user index: {e}")

    def _load_kb(self) -> "KBRegistry":
        """加载知识库

        v0.10.0: 改走 KBRegistry。
        原实现是 `for fp in kb_dir.glob("*.json"): kb[fp.stem] = json.loads(...)`,
        加载是自动的, 但 `search_knowledge_base()` 只认 KB_INDEX_FIELD /
        KB_DISPLAY_FIELD 里登记过的名字, 其余**静默跳过** —— 于是"丢个 json 进去
        就能搜到"是假的, 新库要改三处代码。

        现在: 目录自动发现 → 注册表登记 → 未声明 schema 的库走通用兜底,
        全部可检索。原有 10 个库的 index/display 规则原样迁进 _LEGACY_KB_SCHEMAS,
        行为保持不变。
        """
        reg = KBRegistry()

        # 原有 10 个库的专用 schema —— 保持既有检索/展示行为不变
        for name, (index_fn, display_fn) in _LEGACY_KB_SCHEMAS.items():
            fp = settings.KNOWLEDGE_BASE_DIR / f"{name}.json"
            if not fp.exists():
                continue
            try:
                items = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"KB 加载失败 {name}.json: {e}")
                continue
            if not isinstance(items, list):
                logger.error(f"KB 格式错误 {name}.json: 顶层应为 list")
                continue
            reg.register(name, items, index_fn=index_fn, display_fn=display_fn,
                         source=_first_meta(items, "source"), license=_first_meta(items, "license"),
                         origin="builtin")

        # 再扫一遍目录, 把上面没覆盖到的(即新增的/带 manifest 的)全部注册进来
        reg.load_directory(settings.KNOWLEDGE_BASE_DIR)

        info = reg.describe()
        logger.info(
            f"KB loaded: {info['total_libraries']} libraries, {info['total_items']} items "
            f"(searchable: {len(info['searchable'])})"
        )
        return reg

    # ========== 用户资源 CRUD ==========

    def add_resource(self, resource_id: int, content: str, metadata: Dict = None) -> bool:
        if not content and not metadata:
            return False
        try:
            text_for_index = content or (metadata or {}).get("title", "")
            if not text_for_index:
                return False
            # 同步入口 — 实际项目里调 RAG 的都是 sync (上传/编辑时)
            embedding = self.embedding.embed(text_for_index)
            meta = dict(metadata or {})
            meta["resource_id"] = str(resource_id)
            meta["content_text"] = text_for_index
            meta["embedding_mode"] = self.embedding.mode
            user_id = str(meta.get("user_id", "0"))
            if user_id not in self.user_index:
                self.user_index[user_id] = {}
            self.user_index[user_id][str(resource_id)] = {
                "content": text_for_index,
                "metadata": meta,
                "embedding": embedding,
            }
            self._save_user_index()
            logger.info(f"Added resource {resource_id} (user {user_id}) to RAG: {meta.get('code', '?')} ({self.embedding.mode})")
            return True
        except Exception as e:
            logger.error(f"Failed to add resource: {e}")
            return False

    def update_resource(self, resource_id: int, content: str, metadata: Dict = None) -> bool:
        self.delete_resource(resource_id)
        return self.add_resource(resource_id, content, metadata)

    def delete_resource(self, resource_id: int):
        try:
            for user_id, items in self.user_index.items():
                if str(resource_id) in items:
                    del items[str(resource_id)]
            self._save_user_index()
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
        return False

    # ========== 搜索 ==========

    def search_user_resources(
        self,
        query: str,
        user_id: int,
        top_k: int = 3,
        resource_type: str = None,
    ) -> List[Dict]:
        """搜索用户资源 (按 cosine 相似度 + code 精确匹配 boost)"""
        user_id = str(user_id)
        user_items = self.user_index.get(user_id, {})
        if not user_items:
            return []
        query_codes = set(m.upper() for m in _re.findall(r"[MS]-\d+", query or ""))
        try:
            query_emb = self.embedding.embed(query)
            scored = []
            for rid, item in user_items.items():
                if resource_type and item["metadata"].get("type") != resource_type:
                    continue
                # 跳过维度不匹配的历史索引 (例如用户从 fallback 切到 openai)
                if len(item["embedding"]) != len(query_emb):
                    logger.debug(f"Skip {rid}: dim mismatch ({len(item['embedding'])} vs {len(query_emb)})")
                    continue
                score = cosine(query_emb, item["embedding"])
                item_code = (item["metadata"].get("code") or "").upper()
                if item_code and item_code in query_codes:
                    score += 1.0
                if score > 0.01:
                    scored.append({
                        "content": item["content"],
                        "metadata": item["metadata"],
                        "score": score,
                    })
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def search_knowledge_base(self, query: str, top_k: int = 5) -> List[Dict]:
        """搜索知识库 (entity boost + 关键词打分)

        v0.10.0: 走 KBRegistry。原来的
        `if not index_fn or not display_fn: continue` 会让任何没登记过的库
        静默消失; 现在没声明 schema 的库走通用兜底, 一样能搜到。
        """
        results: List[Dict] = []
        query_tokens = set(tokenize(query))

        # Step 1: entity boost (省+年份 → 强行置顶)
        results.extend(maybe_apply_boost(query, self.knowledge_base))

        # Step 2: 关键词打分
        for kb_name, kbs in self.knowledge_base.items():
            if not kbs.enabled:
                continue
            for item in kbs.items:
                if not isinstance(item, dict):
                    continue
                content = kbs.index_of(item)
                score = keyword_score(query_tokens, content)
                if score > 0:
                    title, body = self._format_result(kb_name, item, kbs.display_of)
                    results.append({
                        "type": kb_name,
                        "title": title,
                        "content": body,
                        "score": score,
                        "data": item,
                        # v0.10.0: 合规元数据随结果透出 (CC BY 4.0 / MIT 内容需署名)
                        "kb_source": kbs.source,
                        "kb_license": kbs.license,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def describe_kb(self) -> Dict:
        """知识库自省 — 给"为什么搜不到"提供答案(原实现只能翻代码)"""
        return self.knowledge_base.describe()

    def _format_result(self, kb_name: str, item: Dict, display_fn) -> tuple[str, str]:
        """生成 title + body

        v0.10.0: 原来这里按库名硬编码了 colleges/majors/cities/career/zhang_quotes/
        zhang_strategy_2026/gaokao_2026 七个分支, 但这些是 v0.7.x 的库名 ——
        v0.8.0 重做成 01_/02_... 之后**没有一个还存在**, 全部走 else, 等于死代码。
        现在标题统一由 KBSource.title_of 推导(优先 name/title), 新库零改动。
        """
        kbs = self.knowledge_base.get(kb_name)
        if kbs is not None:
            title = kbs.title_of(item)
        else:
            title = (item.get("name") or item.get("title") or item.get("category") or "") if isinstance(item, dict) else ""
            title = str(title)[:100]
        body = display_fn(item)
        return title, body

    # ========== 拼 context ==========

    def build_context(self, user_resources: List[Dict], kb_results: List[Dict]) -> str:
        """拼 LLM 用的 context 文本"""
        ctx_parts = []
        if user_resources:
            ctx_parts.append("# 用户的资料和错题 (IMPORTANT: reference by code like M-001, S-001)")
            for r in user_resources:
                meta = r.get("metadata", {})
                code = meta.get("code", "")
                rtype = meta.get("type", "material")
                title = meta.get("title", "")
                subject = meta.get("subject", "")
                kp = meta.get("knowledge_point", "")
                file_path = meta.get("file_path", "")
                label = "错题" if rtype == "mistake" else "学习资料"
                code_str = code if code else f"ID{meta.get('resource_id', '?')}"
                ctx_parts.append(f"\n## [{label} {code_str}] {title}")
                if subject:
                    ctx_parts.append(f"学科: {subject}")
                if kp:
                    ctx_parts.append(f"知识点: {kp}")
                ctx_parts.append(f"内容:\n{r['content'][:1000]}")
                if file_path:
                    ctx_parts.append(f"附件: {file_path} (image/PDF — user has uploaded this file)")
            ctx_parts.append("\n# Instructions: Reference the user's resources by code (M-001, S-001). If they ask about a resource, use the content above.")
        if kb_results:
            ctx_parts.append("\n\n# 知识库检索结果 (built-in: 11 类 KB: colleges / majors / strategy / life_kb / admission / policy / cities / career / zhang_quotes / zhang_strategy_2026 / gaokao_2026)")
            ctx_parts.append("# 重要: 以下内容是用户问题的检索结果, 请优先基于这些内容回答, 不要以'我的知识不是实时的'拒绝。")
            for r in kb_results:
                ctx_parts.append(f"\n{r['content'][:500]}")
        return "\n".join(ctx_parts) if ctx_parts else ""


# 模块级单例
rag_engine = ZhangRAG()
embedding_service = rag_engine.embedding
