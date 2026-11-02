"""命令行入口: 一次索引 + 交互问答。

用法(在仓库根目录):
  .venv/Scripts/python.exe -m pocket_rag.cli                # 交互模式
  .venv/Scripts/python.exe -m pocket_rag.cli "问题..."      # 单问模式
"""

from __future__ import annotations

import sys
from pathlib import Path

from pocket_rag.answer import answer_question, format_answer
from pocket_rag.chunk import chunk_all
from pocket_rag.parse import parse_dir
from pocket_rag.retrieve import Retriever


def build_retriever(docs_dir: Path) -> Retriever:
    """解析 -> 切块 -> 建索引, 打印各阶段数字让用户看得见。"""
    rep = parse_dir(docs_dir)
    print(f"解析: {len(rep.docs)} 篇成功, {len(rep.errors)} 篇失败")
    for e in rep.errors:
        print(f"  (跳过) {e}")
    if not rep.docs:
        sys.exit("没有可用的文档, 退出")

    parents, children = chunk_all(rep.docs)
    print(f"切块: {len(parents)} 个父块, {len(children)} 个子块")

    retriever = Retriever(parents, children)
    mode = "BM25+向量混合" if retriever._embed else "纯 BM25(未配置 embedding, 向量通道自动关闭)"
    print(f"索引完成, 检索模式: {mode}\n")
    return retriever


def main() -> None:
    docs_dir = Path(__file__).resolve().parent.parent / "sample_docs"
    retriever = build_retriever(docs_dir)

    if len(sys.argv) > 1:                                  # 单问模式
        questions = sys.argv[1:]
    else:                                                  # 交互模式
        print("输入问题回车提问, 直接回车退出。")
        questions = None

    if questions:
        for q in questions:
            print(f"\nQ: {q}")
            hits = retriever.query(q)
            ans = answer_question(q, hits)
            print(format_answer(ans))
        return

    while True:
        try:
            q = input("\n问> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        hits = retriever.query(q)
        ans = answer_question(q, hits)
        print(format_answer(ans))


if __name__ == "__main__":
    main()
