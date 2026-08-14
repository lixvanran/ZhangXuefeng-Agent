"""LLM 运行器 - 统一 LLM 调用 + tool 循环
v0.7.5+: 支持 model hint (router 选出来的具体模型)
- run_llm_with_tools: 非流式 (返回完整 result)
- run_llm_stream: 流式 (yield chunk)
v0.8.0+: stop_event 支持中途打断 (Stop 按钮响应延迟从 reasoning 等到 1-2s)
"""
import json
import logging
import asyncio
from typing import Dict, AsyncGenerator, List, Tuple, Optional

from app.agent.llm import llm_client, deep_thinking_client
from app.agent.prompts import TOOLS
from app.agent.tools import execute_tool
from app.agent.pipeline.postprocessor import sanitize_llm_output

logger = logging.getLogger(__name__)


async def _check_stop(stop_event: Optional[asyncio.Event], check_counter: int = 0):
    """检查是否被 Stop 按钮打断 - 每 N 个 chunk 调一次避免频繁"""
    if stop_event is None:
        return
    if stop_event.is_set():
        raise asyncio.CancelledError("user stopped stream")


# ===== 动态模型调用 (跳过 LLMClient 默认 fallback, 自己按 router 的 chain 来) =====

async def _do_chat_with_models(
    primary: str,
    fallback: List[str],
    messages: List[Dict],
    tools: Optional[list] = None,
) -> Dict:
    """按 [primary, *fallback] 顺序调 LLM, 成功就返回
    跟 LLMClient.chat() 类似, 但 primary 是动态传入的
    """
    last_err: Optional[Exception] = None
    models = [primary] + [m for m in fallback if m != primary]
    for m in models:
        try:
            return await llm_client._do_chat(m, messages, tools)
        except Exception as e:
            logger.warning(f"_do_chat_with_models: {m} failed: {e}")
            last_err = e
    return {
        "content": llm_client._fallback_response(last_err or Exception("all failed")),
        "tool_calls": None,
        "finish_reason": "error",
    }


async def _do_stream_with_models(
    primary: str,
    fallback: List[str],
    messages: List[Dict],
    tools: Optional[list] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[str, None]:
    """流式版本 - 按 [primary, *fallback] 顺序
    v0.8.0+: stop_event - 用户 Stop 按钮 set 后, 每个 chunk 之前 yield 之前 check
    """
    models = [primary] + [m for m in fallback if m != primary]
    tried = set()
    for m in models:
        if m in tried:
            continue
        tried.add(m)
        try:
            kwargs = {
                "model": m,
                "messages": messages,
                "temperature": llm_client.temperature,
                "max_tokens": llm_client.max_tokens,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            stream = await llm_client.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                # v0.8.0: 每个 chunk 之前检查 stop
                if stop_event is not None and stop_event.is_set():
                    return  # 静默退出, 让上层 run_llm_stream 看到完整 content 后 yield stopped
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            return
        except Exception as e:
            logger.warning(f"stream {m} failed: {e}")
            continue
    yield llm_client._fallback_response(Exception("all stream failed"))


# ===== 公共入口 =====

async def _execute_tool_calls(tool_calls: list) -> Tuple[List[Dict], List[Dict]]:
    """执行所有 tool calls
    Returns: (tool_calls_log, tool_messages)
    """
    log = []
    messages = []
    for tc in tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except Exception:
            args = {}
        result = await execute_tool(name, args)
        log.append({"tool": name, "args": args, "result": result})
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(result, ensure_ascii=False),
        })
    return log, messages


def _make_assistant_tool_message(response: Dict) -> Dict:
    return {
        "role": "assistant",
        "content": response.get("content") or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in response["tool_calls"]
        ],
    }


def _resolve_model_hint(
    primary: Optional[str],
    fallback: Optional[List[str]],
    deep_thinking: bool,
) -> Tuple[str, List[str]]:
    """解析模型 hint:
    - 显式传 (primary, fallback): 用 router 选出的
    - 传 deep_thinking=True: 用 deep_thinking_client
    - 都不传: 用 llm_client 默认 (self.model + self.fallback_models)
    """
    if primary:
        return primary, fallback or []
    if deep_thinking:
        return deep_thinking_client.model, deep_thinking_client.fallback_models
    return llm_client.model, llm_client.fallback_models


async def run_llm_with_tools(
    messages: List[Dict],
    deep_thinking: bool = False,
    primary_model: Optional[str] = None,
    fallback_models: Optional[List[str]] = None,
) -> Dict:
    """非流式 LLM + tool 循环

    Args:
        messages: 已拼好的 messages (含 system + history + user)
        deep_thinking: 是否用深度思考客户端
        primary_model: 路由选出的主模型 (覆盖默认)
        fallback_models: 主模型挂了后试这些

    Returns: {
        "content": str,
        "reasoning": str,
        "tool_calls": list (log),
        "model_used": str,  # 实际用到的模型
    }
    """
    primary, fallback = _resolve_model_hint(primary_model, fallback_models, deep_thinking)

    # 第一次调用
    if deep_thinking:
        response = await deep_thinking_client.chat(messages, tools=TOOLS)
        model_used = deep_thinking_client.model
    else:
        response = await _do_chat_with_models(primary, fallback, messages, tools=TOOLS)
        # 实际用到的模型, 这里简化: 取 primary (出错时 fallback 链中的)
        model_used = primary

    tool_calls_log: List[Dict] = []
    if response.get("tool_calls"):
        tool_calls_log, tool_messages = await _execute_tool_calls(response["tool_calls"])
        messages.append(_make_assistant_tool_message(response))
        messages.extend(tool_messages)
        # v0.9.6: 二次调用 - **仍然带 tools**, 让 LLM 拿到工具结果后还能继续调
        # (修复: 之前 tools=[] 导致 LLM 调完 describe_file 后只能用文字回答, 不能调 add_mistake)
        if deep_thinking:
            final = await deep_thinking_client.chat(messages, tools=TOOLS)
        else:
            final = await _do_chat_with_models(primary, fallback, messages, tools=TOOLS)
        # v0.9.6: 如果二次调用又有 tool_calls, 最多再执行 1 轮
        # (错题工作流: scan → describe → add_mistake, 共 3 步, 给 3 轮工具执行)
        max_tool_rounds = 3
        for _ in range(max_tool_rounds - 1):
            if not final.get("tool_calls"):
                break
            extra_log, extra_msgs = await _execute_tool_calls(final["tool_calls"])
            tool_calls_log.extend(extra_log)
            messages.append(_make_assistant_tool_message(final))
            messages.extend(extra_msgs)
            if deep_thinking:
                final = await deep_thinking_client.chat(messages, tools=TOOLS)
            else:
                final = await _do_chat_with_models(primary, fallback, messages, tools=TOOLS)
        # 最终不带 tools, 出 markdown 答案
        if deep_thinking:
            last = await deep_thinking_client.chat(messages, tools=[])
        else:
            last = await _do_chat_with_models(primary, fallback, messages, tools=[])
        final["content"] = last["content"]
        if last.get("reasoning") and not final.get("reasoning"):
            final["reasoning"] = last["reasoning"]
        response["content"] = final["content"]
        if final.get("reasoning") and not response.get("reasoning"):
            response["reasoning"] = final["reasoning"]

    return {
        "content": response.get("content", ""),
        "reasoning": response.get("reasoning", ""),
        "tool_calls": tool_calls_log,
        "model_used": model_used,
    }


async def run_llm_stream(
    messages: List[Dict],
    deep_thinking: bool = False,
    primary_model: Optional[str] = None,
    fallback_models: Optional[List[str]] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[Tuple[str, any], None]:
    """流式 LLM

    Yields: (event_type, data) 其中 event_type ∈:
      - "rag_summary"  → dict  (RAG 用量, 一次性)
      - "reasoning"    → str   (思考过程增量)
      - "tool_call"    → dict  (工具调用 + 结果, 一次性)
      - "content"      → str   (最终回答增量, 已 sanitize)
      - "done"         → str   (完整 content + reasoning + model_used)
      - "stopped"      → str   (用户中途叫停)

    v0.8.0+: stop_event - 用户按 Stop 按钮会 set, 流每 N 个 chunk check 一次
    """
    primary, fallback = _resolve_model_hint(primary_model, fallback_models, deep_thinking)

    # 1) 第一次非流式调用, 拿 tool_calls + 早期 reasoning
    #   (Stop 按钮在这里也能中断, 因为它就是一次 await)
    if stop_event is not None and stop_event.is_set():
        yield ("stopped", "用户中途叫停 (LLM 启动前)")
        return
    if deep_thinking:
        response = await deep_thinking_client.chat(messages, tools=TOOLS)
        model_used = deep_thinking_client.model
    else:
        response = await _do_chat_with_models(primary, fallback, messages, tools=TOOLS)
        model_used = primary

    if stop_event is not None and stop_event.is_set():
        yield ("stopped", "用户中途叫停 (LLM 返回答前)")
        return

    if response.get("reasoning"):
        yield ("reasoning", response["reasoning"])

    # 2) 如果有 tool_calls, 执行
    # v0.9.6: 多轮工具循环 — 错题工作流 scan → describe → add_mistake 共 3 步
    # 之前只支持 1 轮, LLM 调完 describe_file 拿到结果后第二轮 tools=[] 不能调 add_mistake
    all_tool_logs: List[Dict] = []
    max_tool_rounds = 3
    for _round in range(max_tool_rounds):
        if not response.get("tool_calls"):
            break
        yield ("tool_call", [
            {"name": tc.function.name, "args": json.loads(tc.function.arguments) if tc.function.arguments else {}}
            for tc in response["tool_calls"]
        ])
        tool_calls_log, tool_messages = await _execute_tool_calls(response["tool_calls"])
        all_tool_logs.extend(tool_calls_log)
        yield ("tool_result", tool_calls_log)
        messages.append(_make_assistant_tool_message(response))
        messages.extend(tool_messages)
        # 下一轮: 让 LLM 看到工具结果后能继续调
        if deep_thinking:
            response = await deep_thinking_client.chat(messages, tools=TOOLS)
        else:
            response = await _do_chat_with_models(primary, fallback, messages, tools=TOOLS)
        if response.get("reasoning"):
            yield ("reasoning", response["reasoning"])

    # 3) 流式最终回答 (不带 tools, 强制出 markdown 答案)
    full_content = ""
    reasoning_text = response.get("reasoning", "") or ""
    chunk_counter = 0
    if deep_thinking:
        async for ev_type, ev_data in deep_thinking_client.stream_chat(messages, stop_event=stop_event):
            chunk_counter += 1
            # v0.8.0: 每个 chunk 之前检查 stop, 1 个 token 级别响应
            if stop_event is not None and stop_event.is_set():
                yield ("stopped", "用户中途叫停 (deep_thinking 流中)")
                return
            if ev_type == "reasoning":
                reasoning_text += ev_data
                yield ("reasoning", ev_data)
            elif ev_type == "content":
                full_content += ev_data
                clean = sanitize_llm_output(ev_data)
                if clean:
                    yield ("content", clean)
            elif ev_type == "error":
                yield ("content", ev_data)
            elif ev_type == "stopped":
                # deep_thinking_client 内部已经 stop, 透传
                yield ("stopped", ev_data)
                return
    else:
        # 包装 _do_stream_with_models 支持 stop_event
        async for chunk in _do_stream_with_models(primary, fallback, messages, stop_event=stop_event):
            chunk_counter += 1
            if stop_event is not None and stop_event.is_set():
                yield ("stopped", "用户中途叫停 (主链路流中)")
                return
            full_content += chunk
            clean = sanitize_llm_output(chunk)
            if clean:
                yield ("content", clean)

    # 4) 处理 [THINKING]...[/THINKING] 包埋
    import re
    think_match = re.search(r"\[THINKING\](.*?)\[/THINKING\]", full_content, re.DOTALL)
    if think_match:
        thinking_text = think_match.group(1).strip()
        clean_content = re.sub(r"\[THINKING\].*?\[/THINKING\]\s*", "", full_content, flags=re.DOTALL).strip()
        if not reasoning_text:
            reasoning_text = thinking_text
        full_content = clean_content

    yield ("done", {"content": full_content, "reasoning": reasoning_text, "model_used": model_used})
