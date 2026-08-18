"""向量化索引
v0.9.8: 统一用 1 个 LLM_API_KEY (OpenRouter) 跑全部 LLM/Embedding
- 默认 (无 LLM_API_KEY): 用纯 Python TF-IDF 假 embedding (512 维, hash + log)
  * 优点: 零依赖, 启动即可用
  * 缺点: 语义召回差, 基本是关键词共现
- 选了 LLM_API_KEY: 调 OpenRouter 的 openai/text-embedding-3-small (1536 维, 真正语义)
  * 通过 OpenRouter 一个 key 走通, 不需要单独的 OpenAI key
  * 切换后需要重跑 add_resource 才能重新索引
"""
import hashlib
import logging
import math
from typing import List, Dict

from app.agent.rag.tokenizer import tokenize
from app.core.config import settings

logger = logging.getLogger(__name__)

# 两套 embedding 维度不一样, 缓存里必须区分
TFIDF_DIM = 512
OPENAI_DIM = 1536


def _hash_dim(text: str, dim: int) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % dim


class EmbeddingService:
    """Embedding 入口 — 启动时根据 settings 选模式
    - openai: 走 OpenRouter (openai/text-embedding-3-small)
    - fallback: 纯 Python TF-IDF
    """

    def __init__(self):
        # v0.9.8: 改用 LLM_API_KEY 走 OpenRouter, 不再依赖 OPENAI_API_KEY
        if settings.LLM_API_KEY:
            self.mode = "openai"
            self.dim = OPENAI_DIM
            self.model = "openai/text-embedding-3-small"
            logger.info(f"Embedding: OpenRouter ({self.model}, dim={self.dim}) — 共用 LLM_API_KEY")
        else:
            self.mode = "fallback"
            self.dim = TFIDF_DIM
            logger.info(f"Embedding: fallback TF-IDF (dim={self.dim}, 语义召回有限但零依赖)")

    def embed(self, text: str) -> List[float]:
        if self.mode == "openai":
            return self._openai_embed(text)
        return self._tfidf_vector(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]

    # ===== OpenRouter (OpenAI-compatible embeddings) =====
    def _openai_embed(self, text: str) -> List[float]:
        """同步版, 在 async 上下文里走 to_thread"""
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.LLM_API_KEY,  # v0.9.8: 共用 OpenRouter key
                base_url=settings.LLM_BASE_URL,  # 默认 https://openrouter.ai/api/v1
            )
            resp = client.embeddings.create(
                model=self.model,
                input=text,
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.error(f"OpenRouter embedding failed: {e}, falling back to TF-IDF")
            return self._tfidf_vector(text)

    async def aembed(self, text: str) -> List[float]:
        """异步版 — 实际 RAG 调用走这个"""
        if self.mode == "openai":
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=settings.LLM_API_KEY,  # v0.9.8: 共用 OpenRouter key
                    base_url=settings.LLM_BASE_URL,
                )
                resp = await client.embeddings.create(
                    model=self.model,
                    input=text,
                )
                return resp.data[0].embedding
            except Exception as e:
                logger.error(f"OpenRouter embedding failed: {e}, falling back to TF-IDF")
        return self._tfidf_vector(text)

    # ===== Fallback: TF-IDF =====
    def _tfidf_vector(self, text: str) -> List[float]:
        tokens = tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        vec = [0.0] * self.dim
        for tok, cnt in tf.items():
            idx = _hash_dim(tok, self.dim)
            vec[idx] += math.log(1 + cnt)
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
