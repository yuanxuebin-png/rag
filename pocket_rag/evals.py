"""评测: 15 条问答对(12 条库内可答 + 3 条库外应拒答), 三层自动判定。

判定分三层, 各自衡量不同环节:
1. 检索命中率(离线, 不调模型): 金标父块是否进入 top-4
   -> 衡量切块+检索环节
2. 拒答正确率(离线): 库外问题是否触发拒答、库内问题是否误拒
   -> 衡量阈值设定
3. 答案关键词命中(在线, 每题一次模型调用): 答案文本是否包含关键事实
   -> 衡量生成环节(不做开放式打分, 关键词判定可复现)

用法:
  python -m pocket_rag.evals --offline     # 只跑前两层, 秒级, 不花钱
  python -m pocket_rag.evals               # 全量三层
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from pocket_rag.answer import answer_question
from pocket_rag.chunk import chunk_all
from pocket_rag.parse import parse_dir
from pocket_rag.retrieve import Retriever


@dataclass
class QA:
    question: str
    keywords: tuple[str, ...]        # 答案必须包含的关键词(全部命中才算过)
    gold: str                        # 金标父块 pid 的子串, 如 "git-notes.md#撤销操作"
    refuse: bool = False             # True = 库外问题, 应拒答


CASES: list[QA] = [
    # ---- python-venv.md ----
    QA("为什么要给每个项目建虚拟环境", ("隔离", "依赖"), "python-venv.md#为什么要用虚拟环境"),
    QA("pip 装了包但 import 报错, 怎么排查", ("pip list", "executable"), "python-venv.md#常见坑"),
    # ---- git-notes.md ----
    QA("已经 push 出去的错误提交怎么撤销", ("revert",), "git-notes.md#撤销操作"),
    QA(".gitignore 加了文件还是被跟踪, 怎么办", ("rm --cached",), "git-notes.md#.gitignore 与大文件"),
    QA("合并冲突时文件里会出现什么标记", ("<<<<<<<", ">>>>>>>"), "git-notes.md#分支"),
    # ---- langchain-notes.md ----
    QA("DeepSeek 上 max_tokens 怎么写才能生效", ("extra_body",), "langchain-notes.md#DeepSeek 兼容层的两个大坑"),
    QA("with_structured_output 在 DeepSeek 上报 400 怎么解决", ("function_calling",), "langchain-notes.md#DeepSeek 兼容层的两个大坑"),
    QA("手写 token 估算公式对中文准吗", ("高估",), "langchain-notes.md#上下文管理"),
    # ---- http-basics.txt ----
    QA("401 和 403 有什么区别", ("未认证", "没权限"), "http-basics.txt"),
    QA("哪些 HTTP 方法是幂等的", ("幂等", "GET"), "http-basics.txt"),
    # ---- coding-style.md ----
    QA("可变默认参数有什么坑, 正确写法是什么", ("None", "共享"), "coding-style.md#函数设计"),
    QA("异常处理的几条原则", ("裸", "吞"), "coding-style.md#异常处理"),
    # ---- 库外问题: 应拒答 ----
    QA("北京明天天气怎么样", (), "", refuse=True),
    QA("怎么做红烧肉", (), "", refuse=True),
    QA("世界杯冠军是哪个国家", (), "", refuse=True),
]


@dataclass
class CaseResult:
    qa: QA
    retrieval_hit: bool | None       # None = 拒答题不参与
    refused: bool
    keyword_hit: bool | None         # None = 拒答或离线模式


def run(model=None, online: bool = True) -> list[CaseResult]:
    docs_dir = Path(__file__).resolve().parent.parent / "sample_docs"
    rep = parse_dir(docs_dir)
    parents, children = chunk_all(rep.docs)
    retriever = Retriever(parents, children)

    results: list[CaseResult] = []
    for qa in CASES:
        hits = retriever.query(qa.question)
        refused = hits is None

        if qa.refuse:
            results.append(CaseResult(qa, None, refused, None))
            continue

        hit_pids = [h.parent.pid for h in hits] if hits else []
        r_hit = any(qa.gold in pid for pid in hit_pids)
        k_hit = None
        if online and not refused:
            ans = answer_question(qa.question, hits, model=model)
            k_hit = all(k.lower() in ans.text.lower() for k in qa.keywords)
        results.append(CaseResult(qa, r_hit, refused, k_hit))
    return results


def report(results: list[CaseResult]) -> str:
    ans_cases = [r for r in results if not r.qa.refuse]
    ref_cases = [r for r in results if r.qa.refuse]
    ret_hit = sum(r.retrieval_hit for r in ans_cases)
    refused_ok = sum(r.refused == r.qa.refuse for r in results)
    kw = [r for r in ans_cases if r.keyword_hit is not None]
    kw_hit = sum(r.keyword_hit for r in kw)

    lines = [
        "| # | 问题 | 检索命中 | 拒答正确 | 关键词 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        fmt = lambda b: "✓" if b else "✗" if b is False else "—"
        lines.append(f"| {i} | {r.qa.question[:18]}… | {fmt(r.retrieval_hit)} "
                     f"| {fmt(r.refused == r.qa.refuse)} | {fmt(r.keyword_hit)} |")
    lines += [
        "",
        f"- 检索命中率(库内 12 条, 金标父块进 top-4): **{ret_hit}/{len(ans_cases)}**",
        f"- 拒答判定正确率(15 条含误拒检查): **{refused_ok}/{len(results)}**",
        f"- 答案关键词命中(库内且未误拒的 {len(kw)} 条): **{kw_hit}/{len(kw)}**",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="跳过模型调用, 只测检索与拒答")
    args = ap.parse_args()

    model = None
    if not args.offline:
        model = __import__("pocket_rag.answer", fromlist=["_load_model"])._load_model()

    results = run(model=model, online=not args.offline)
    text = report(results)
    print(text)

    if not args.offline:
        out = Path(__file__).resolve().parent.parent / "docs" / "eval_result.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text("# pocket-rag 评测结果(自动生成)\n\n" + text + "\n", encoding="utf-8")
        print(f"\n留档: {out}")


if __name__ == "__main__":
    main()
