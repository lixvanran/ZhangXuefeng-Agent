"""知识库可插拔注册表 — v0.10.0 新增

## 为什么要有这个

原实现里新增一个知识库文件要改 `engine.py` 三处:
1. `KB_INDEX_FIELD`  加一条 lambda (索引文本怎么抽)
2. `KB_DISPLAY_FIELD` 加一条 lambda (展示文本怎么抽)
3. `_format_result()`    加一个 if/elif 分支 (标题怎么拼)

漏改任何一处, 后果都不报错 —— `search_knowledge_base()` 里
`if not index_fn or not display_fn: continue` 会把这个知识库
**静默跳过**, 文件加载了但永远搜不到。README 里"无需改代码"的说法
只对"加载"成立, 对"搜索"是假的。

## 这个模块解决什么

把上面三处硬编码收敛成一个声明式注册表:

- **零代码扩库**: 丢一个 `11_xxx.json` 进 `knowledge_base/`, 默认就能被搜到。
  想自定义展示, 就写一份同名 `.manifest.json` 声明字段, 同样不用改代码。
- **有 manifest 就用 manifest, 没 manifest 就用通用兜底**, 不再有"静默跳过"。
- **运行时注册**: `registry.register(...)` 可在进程内挂载新的 KB (测试/热加载用)。
- **可观测**: `describe()` 报告每个库的条目数、来源、license、是否可检索,
  排查"为什么搜不到"不用再翻代码。
- **保留合规元数据**: `source` / `license` 随条目一路带到展示层和检索结果,
  对 v0.9.8 引入的 CC BY 4.0 / MIT 开源内容是硬要求。
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 抽取索引/展示文本时, 优先尝试的字段名(按顺序)
_TITLE_FIELDS = ("name", "title", "text", "context", "summary", "content", "category", "id")
# 通用兜底里, 参与索引的字段白名单(优先); 为空则用"所有标量字段"
_GENERIC_INDEX_FIELDS = (
    "name", "title", "text", "context", "summary", "content", "category",
    "type", "name_zh", "comment", "school_name", "province", "city", "tier",
    "features", "scope", "topic", "tags", "key_points", "famous_majors",
)


def _as_text(value: Any) -> str:
    """把任意 JSON 值摊平成可检索/可展示的文本"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(v) for v in value if v is not None)
    if isinstance(value, dict):
        return " ".join(_as_text(v) for v in value.values() if v is not None)
    return str(value)


def generic_index_text(item: Dict) -> str:
    """通用索引文本: 白名单字段优先, 都没命中就把所有标量字段拼上"""
    if not isinstance(item, dict):
        return _as_text(item)
    parts = [_as_text(item.get(f)) for f in _GENERIC_INDEX_FIELDS if item.get(f)]
    if parts:
        return " ".join(parts)
    return " ".join(_as_text(v) for v in item.values())


def generic_display_text(item: Dict) -> str:
    """通用展示文本: 取第一个能当标题的字段当标题, 其余当正文"""
    if not isinstance(item, dict):
        return _as_text(item)
    title = ""
    for f in _TITLE_FIELDS:
        v = _as_text(item.get(f))
        if v:
            title = v
            break
    title = title[:100]
    body_bits = []
    for f, v in item.items():
        if f in ("id",):
            continue
        text = _as_text(v)
        if not text or text == title:
            continue
        body_bits.append(f"{f}: {text}")
    body = "\n".join(body_bits)
    src = _as_text(item.get("source"))
    lic = _as_text(item.get("license"))
    if src or lic:
        body += f"\n[来源: {src or '?'} / {lic or '?'}]"
    return f"{title}\n{body}" if body else title


@dataclass
class KBSource:
    """一个已注册的知识库"""
    name: str
    items: List[Dict] = field(default_factory=list)
    index_fn: Optional[Callable[[Dict], str]] = None
    display_fn: Optional[Callable[[Dict], str]] = None
    source: str = ""
    license: str = ""
    enabled: bool = True
    # 自动生成的条目(来自 entry 字段的 source/license)合并进来
    origin: str = "custom"  # file | runtime | builtin

    def index_of(self, item: Dict) -> str:
        fn = self.index_fn or generic_index_text
        try:
            return fn(item)
        except Exception as e:  # 单条坏数据不能拖垮整个库
            logger.warning(f"KB '{self.name}' index_fn failed on one item: {e}")
            return ""

    def display_of(self, item: Dict) -> str:
        fn = self.display_fn or generic_display_text
        try:
            return fn(item)
        except Exception as e:
            logger.warning(f"KB '{self.name}' display_fn failed on one item: {e}")
            return _as_text(item)

    def title_of(self, item: Dict) -> str:
        """标题: 优先 name/title, 否则取展示文本首行"""
        if isinstance(item, dict):
            for f in ("name", "title"):
                v = _as_text(item.get(f))
                if v:
                    return v[:100]
        return self.display_of(item).split("\n", 1)[0][:100]

    def to_meta(self) -> Dict:
        return {
            "name": self.name,
            "items": len(self.items),
            "source": self.source,
            "license": self.license,
            "enabled": self.enabled,
            "origin": self.origin,
            "custom_schema": bool(self.index_fn or self.display_fn),
        }


class KBRegistry:
    """知识库注册表 — 全局单例由 engine.py 持有"""

    def __init__(self):
        self._sources: Dict[str, KBSource] = {}

    # ---------- 注册 ----------

    def register(
        self,
        name: str,
        items: List[Dict],
        index_fn: Optional[Callable[[Dict], str]] = None,
        display_fn: Optional[Callable[[Dict], str]] = None,
        source: str = "",
        license: str = "",
        enabled: bool = True,
        origin: str = "runtime",
    ) -> KBSource:
        """注册/覆盖一个知识库。重复 name 会覆盖并打日志。"""
        if not isinstance(items, list):
            raise TypeError(f"KB '{name}': items 必须是 list, 收到 {type(items).__name__}")
        clean = [it for it in items if isinstance(it, dict)]
        dropped = len(items) - len(clean)
        if dropped:
            logger.warning(f"KB '{name}': 丢弃 {dropped} 条非 dict 记录")
        if name in self._sources:
            logger.info(f"KB '{name}': 覆盖已有注册({len(self._sources[name].items)} -> {len(clean)} 条)")
        src = KBSource(
            name=name, items=clean, index_fn=index_fn, display_fn=display_fn,
            source=source, license=license, enabled=enabled, origin=origin,
        )
        self._sources[name] = src
        logger.info(
            f"KB registered: {name} ({len(clean)} 条, origin={origin}, "
            f"source={source or '?'}, license={license or '?'}, "
            f"schema={'custom' if (index_fn or display_fn) else 'generic'})"
        )
        return src

    def unregister(self, name: str) -> bool:
        if name in self._sources:
            del self._sources[name]
            logger.info(f"KB unregistered: {name}")
            return True
        return False

    # ---------- 目录加载 ----------

    def load_directory(self, kb_dir: Path) -> "KBRegistry":
        """扫描目录, 自动发现并注册所有 *.json

        - `NN_name.json`            → 知识库本体
        - `NN_name.manifest.json`  → 可选, 声明该库的 index/display/source/license
          (manifest 自身不会被当成知识库)
        """
        kb_dir = Path(kb_dir)
        if not kb_dir.exists():
            logger.warning(f"knowledge_base dir not found: {kb_dir}")
            return self

        manifests = {}
        for mp in sorted(kb_dir.glob("*.manifest.json")):
            try:
                manifests[mp.name[: -len(".manifest.json")]] = json.loads(
                    mp.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"KB manifest 解析失败 {mp.name}: {e}")

        for fp in sorted(kb_dir.glob("*.json")):
            if fp.name.endswith(".manifest.json"):
                continue
            stem = fp.stem
            try:
                items = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"KB 加载失败 {fp.name}: {e} — 该文件被跳过")
                continue
            if isinstance(items, dict):
                # 允许 {"items": [...], "source": ..., "license": ...} 这种带壳格式
                man = items.get("_meta") or manifests.get(stem) or {}
                items = items.get("items", [])
            else:
                man = manifests.get(stem) or {}

            if not isinstance(items, list):
                logger.error(f"KB 格式错误 {fp.name}: 顶层应为 list, 收到 {type(items).__name__} — 已跳过")
                continue

            src = man.get("source") or _infer_source(items)
            lic = man.get("license") or _infer_license(items)
            self.register(
                name=stem,
                items=items,
                index_fn=man.get("index_fields") and _fields_indexer(man["index_fields"]),
                display_fn=man.get("display_fields") and _fields_displayer(man["display_fields"]),
                source=src,
                license=lic,
                enabled=bool(man.get("enabled", True)),
                origin="file",
            )
        return self

    # ---------- 访问 ----------

    def __contains__(self, name: str) -> bool:
        return name in self._sources

    def __getitem__(self, name: str) -> KBSource:
        return self._sources[name]

    def get(self, name: str) -> Optional[KBSource]:
        return self._sources.get(name)

    def items(self):
        """(name, KBSource) 对, 供兼容旧的 .knowledge_base.items() 用法"""
        return self._sources.items()

    @property
    def names(self) -> List[str]:
        return list(self._sources.keys())

    def describe(self) -> Dict:
        """自省: 每个库的规模/来源/license/schema, 排查"搜不到"用"""
        sources = [s.to_meta() for s in self._sources.values()]
        return {
            "total_libraries": len(sources),
            "total_items": sum(s["items"] for s in sources),
            "libraries": sources,
            "searchable": [s["name"] for s in sources if s["enabled"]],
        }


# ===== manifest 字段 → 函数 =====

def _fields_indexer(fields: List[str]) -> Callable[[Dict], str]:
    """manifest 里声明 index_fields: ["text", "tags"] → 拼成索引文本"""
    def _fn(item: Dict) -> str:
        if not isinstance(item, dict):
            return _as_text(item)
        return " ".join(_as_text(item.get(f)) for f in fields if item.get(f))
    return _fn


def _fields_displayer(fields: List[str]) -> Callable[[Dict], str]:
    """manifest 里声明 display_fields → 逐行渲染成正文"""
    def _fn(item: Dict) -> str:
        if not isinstance(item, dict):
            return _as_text(item)
        lines = []
        for f in fields:
            v = _as_text(item.get(f))
            if v:
                lines.append(f"{f}: {v}")
        return "\n".join(lines)
    return _fn


# ===== 元数据推断 =====

def _infer_source(items: List[Dict]) -> str:
    for it in items[:20]:
        if isinstance(it, dict) and it.get("source"):
            return str(it["source"])
    return ""


def _infer_license(items: List[Dict]) -> str:
    for it in items[:20]:
        if isinstance(it, dict) and it.get("license"):
            return str(it["license"])
    return ""
