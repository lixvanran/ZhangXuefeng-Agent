"""向量化索引
- 默认 (无 OPENAI_API_KEY): 用纯 Python TF-IDF 假 embedding (512 维, hash + log)
  * 优点: 零依赖, 启动即可用
  * 缺点: 语义召回差, 基本是关键词共现
- 选了 OPENAI_API_KEY: 调 text-embedding-3-small (1536 维, 真正语义)
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
    - openai: 走 OpenAI 真实 embedding
    - fallback: 纯 Python TF-IDF
    """

    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.mode = "openai"
            self.dim = OPENAI_DIM
            logger.info(f"Embedding: OpenAI ({settings.OPENAI_EMBEDDING_MODEL}, dim={self.dim})")
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

    # ===== OpenAI =====
    def _openai_embed(self, text: str) -> List[float]:
        """同步版, 在 async 上下文里走 to_thread"""
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
            resp = client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=text,
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}, falling back to TF-IDF")
            return self._tfidf_vector(text)

    async def aembed(self, text: str) -> List[float]:
        """异步版 — 实际 RAG 调用走这个"""
        if self.mode == "openai":
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_BASE_URL,
                )
                resp = await client.embeddings.create(
                    model=settings.OPENAI_EMBEDDING_MODEL,
                    input=text,
                )
                return resp.data[0].embedding
            except Exception as e:
                logger.error(f"OpenAI embedding failed: {e}, falling back to TF-IDF")
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
