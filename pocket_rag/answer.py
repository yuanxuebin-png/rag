"""答案生成: 检索到的父块拼进提示词, 模型只准基于它们作答并标注引用编号。

约束设计的三个要点
------------------
1. **只准用给定材料**: 提示词里明确「材料之外的知识不要用」, 这是控制
   RAG 幻觉的第一道闸; 检索拒答时根本不调模型, 是第二道。
2. **引用编号强制**: 每句结论后面跟 [1][2], 来源信息在答案末尾回显,
   用户可以自己点开原文件核对——可核对性比流畅性重要。
3. **DeepSeek 兼容坑照搬主项目结论**: 限长一律 extra_body={"max_tokens": N},
   直接传 max_tokens 会被改名成 max_completion_tokens 然后被静默丢弃。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pocket_rag.retrieve import Hit

REFUSAL = "知识库中没有找到与该问题相关的内容，无法回答。"


@dataclass
class Answer:
    text: str                  # 模型生成的答案(带 [n] 引用)
    sources: list[str]         # 按引用编号对应的来源描述, 如 "p3:git-notes.md#撤销操作"
    refused: bool              # 是否拒答
    n_hits: int                # 检索命中父块数


def _load_model():
    """从 .env 加载 DeepSeek 配置, 和主项目同一套环境变量约定。"""
    from dotenv import load_dotenv
    load_dotenv()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.environ.get("RAG_MODEL", "deepseek-chat"),
        temperature=0,
        timeout=float(os.environ.get("MODEL_TIMEOUT", "60")),
        extra_body={"max_tokens": 800},       # DeepSeek 限长的唯一正确写法
    )


PROMPT_TMPL = """你是个人知识库问答助手。严格根据下面编号的材料回答问题。

规则:
1. 只用材料里的信息, 材料里没有的不要编。
2. 每个关键结论后面标注来源编号, 如 [1] 或 [2][3]。
3. 材料之间矛盾时, 指出矛盾而不是选边。

材料:
{context}

问题: {question}

回答:"""


def answer_question(question: str, hits: list[Hit] | None, model=None) -> Answer:
    """检索结果 -> 带引用的答案。hits 为 None(拒答信号)时不调模型直接拒答。"""
    if not hits:
        return Answer(text=REFUSAL, sources=[], refused=True, n_hits=0)

    context = "\n\n".join(
        f"[{i + 1}] {h.parent.text}" for i, h in enumerate(hits)
    )
    prompt = PROMPT_TMPL.format(context=context, question=question)

    if model is None:
        model = _load_model()
    text = model.invoke(prompt).content.strip()

    return Answer(
        text=text,
        sources=[h.parent.pid for h in hits],
        refused=False,
        n_hits=len(hits),
    )


def format_answer(ans: Answer) -> str:
    """终端展示格式: 答案 + 溯源清单。"""
    lines = [ans.text, ""]
    if ans.sources:
        lines.append("来源:")
        for i, s in enumerate(ans.sources, 1):
            lines.append(f"  [{i}] {s}")
    return "\n".join(lines)
