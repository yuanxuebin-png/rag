"""父子块切分: 一个文件 -> 父块(语义完整的节) + 子块(检索用的小片段)。

为什么切两层(核心设计)
----------------------
检索命中要靠「小而准」: 200 字左右的子块, 关键词密度高, 向量/BM25 都好匹配。
但直接把 200 字塞给大模型当上下文, 往往缺前因后果, 答案容易飘。
所以: 用子块检索, 命中后返回它所属的父块(整个小节)给模型——
「小块定位, 大块作答」, 这是父子块的全部意义。

切分规则
--------
- md: 按 # / ## 标题切成节, 标题就是父块的名字
- txt: 没有标题, 按空行段落聚合, 每 3 段左右算一节
- 单个父块超过 MAX_PARENT_CHARS 时按段落续切, 防止超长节把上下文撑爆
- 子块在节内按句子滑窗: 约 CHILD_SIZE 字, 重叠 CHILD_OVERLAP 字, 保住跨句语义
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pocket_rag.parse import ParsedDoc, parse_dir

MAX_PARENT_CHARS = 1200   # 父块(节)上限, 超过按段落续切
CHILD_SIZE = 200          # 子块目标长度(字符, 中文一字符≈一词)
CHILD_OVERLAP = 40        # 相邻子块重叠, 防止答案正好被切断

_HEAD_RE = re.compile(r"^(#{1,6})\s+(.+)$")   # md 标题行


@dataclass
class Parent:
    """父块: 给大模型看的语义完整片段。"""

    pid: str          # 形如 "git-notes.md#撤销操作"
    text: str         # 标题 + 正文
    source: str       # 来源文件名(溯源用)
    title: str        # 节标题


@dataclass
class Child:
    """子块: 只用来被检索命中, 不直接给模型。"""

    cid: str          # 形如 "p3#0"
    text: str
    parent_pid: str


def _sections(doc: ParsedDoc) -> list[tuple[str, str]]:
    """把一篇文档切成 (节标题, 节正文) 列表。

    md 按标题行切; txt 没标题, 用「(untitled)」当唯一节名, 靠段落聚合兜底。
    """
    lines = doc.text.splitlines()
    if doc.kind == "txt":
        return [("(untitled)", doc.text)]
    sections: list[tuple[str, str]] = []
    cur_title, cur_body = "(前言)", []
    for line in lines:
        m = _HEAD_RE.match(line)
        if m:
            if "\n".join(cur_body).strip():
                sections.append((cur_title, "\n".join(cur_body)))
            cur_title, cur_body = m.group(2).strip(), []
        else:
            cur_body.append(line)
    if "\n".join(cur_body).strip():
        sections.append((cur_title, "\n".join(cur_body)))
    return sections or [("(untitled)", doc.text)]


def _split_long(text: str) -> list[str]:
    """父块超长时按段落(空行)续切, 每段尽量贴着 MAX_PARENT_CHARS。"""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for p in paras:
        if buf and size + len(p) > MAX_PARENT_CHARS:
            out.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p) + 2
    if buf:
        out.append("\n\n".join(buf))
    return out or [text]


def _children_of(body: str) -> list[str]:
    """节内滑窗切子块: 句边界优先, 兜底硬切。"""
    # 按中文句号/问号/叹号/换行切句, 保留分隔符
    sentences = [s for s in re.split(r"(?<=[。！？!?\n])", body) if s.strip()]
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) > CHILD_SIZE:
            chunks.append(buf.strip())
            buf = buf[-CHILD_OVERLAP:]          # 带着尾部重叠开始下一块
        buf += s
    if buf.strip():
        chunks.append(buf.strip())
    # 单句超过 1.5 倍 CHILD_SIZE 的兜底硬切(比如长代码行/长 URL)
    final: list[str] = []
    for c in chunks:
        while len(c) > CHILD_SIZE * 1.5:
            final.append(c[:CHILD_SIZE])
            c = c[CHILD_SIZE - CHILD_OVERLAP:]
        if c.strip():
            final.append(c)
    return final


def chunk_doc(doc: ParsedDoc) -> tuple[list[Parent], list[Child]]:
    """一篇文档 -> (父块列表, 子块列表)。子块通过 parent_pid 指回父块。"""
    parents: list[Parent] = []
    children: list[Child] = []
    used: dict[str, int] = {}                    # 标题去重计数(同名节)
    for title, body in _sections(doc):
        for part in _split_long(body):
            n = used.get(title, 0)
            used[title] = n + 1
            pid = f"{doc.source}#{title}" + (f"({n + 1})" if n else "")
            text = f"【{title}】\n{part.strip()}" if title != "(untitled)" else part.strip()
            parents.append(Parent(pid=pid, text=text, source=doc.source, title=title))
            for i, c in enumerate(_children_of(part)):
                children.append(Child(cid=f"{pid}#{i}", text=c, parent_pid=pid))
    return parents, children


def chunk_all(docs: list[ParsedDoc]) -> tuple[list[Parent], list[Child]]:
    """批量切分 + 全局编号(p0, p1, ... / c0, c1, ...)。"""
    all_parents: list[Parent] = []
    all_children: list[Child] = []
    for doc in docs:
        ps, cs = chunk_doc(doc)
        all_parents.extend(ps)
        all_children.extend(cs)
    for i, p in enumerate(all_parents):
        p.pid = f"p{i}:{p.pid}"                 # 前缀全局序号, 日志好读
    pid_map = {p.pid.split(":", 1)[1]: p.pid for p in all_parents}
    for i, c in enumerate(all_children):
        c.cid = f"c{i}"
        c.parent_pid = pid_map[c.parent_pid]
    return all_parents, all_children


if __name__ == "__main__":
    demo = Path(__file__).resolve().parent.parent / "sample_docs"
    rep = parse_dir(demo)
    parents, children = chunk_all(rep.docs)
    print(f"{len(rep.docs)} 篇文档 -> {len(parents)} 个父块, {len(children)} 个子块")
    print("\n父块示例:")
    for p in parents[:4]:
        print(f"  {p.pid} ({len(p.text)} 字)")
    print("\n子块示例(第 0 个的全部内容):")
    print(" ", children[0].text)
    print("\n父子对应抽查:")
    print(f"  {children[0].cid} -> {children[0].parent_pid}")
