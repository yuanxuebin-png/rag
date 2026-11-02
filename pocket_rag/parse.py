"""多格式文档解析: md / txt / pdf -> 统一的纯文本。

设计取舍(低配版)
----------------
- md 不做完整的 AST 解析, 保留原始文本: 标题行(# / ##)是后面「父子块」
  切分的锚点, 扔掉就切不准了
- pdf 用 pdfplumber 逐页抽取文字层; 扫描件(纯图片)没有文字层, 属于
  v2 的 OCR 范围, 这里明确检测并给出可读的报错, 不假装能解析
- 解析失败(编码/损坏文件)返回空列表并在 errors 里记原因, 不让一个坏文件
  拖垮整个索引流程
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".md", ".txt", ".pdf"}


@dataclass
class ParsedDoc:
    """一个解析成功的文件 -> 一段完整纯文本 + 元信息。"""

    text: str          # 完整纯文本(保留标题行)
    source: str        # 相对来源路径, 用于答案溯源引用
    kind: str          # md / txt / pdf


@dataclass
class ParseReport:
    """批量解析的结果: 成功的 + 失败原因清单。"""

    docs: list[ParsedDoc] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)   # "文件名: 原因"


def parse_file(path: Path) -> ParsedDoc:
    """解析单个文件。抛出的异常由 parse_dir 收口, 这里只管解析。"""
    suffix = path.suffix.lower()
    if suffix == ".md" or suffix == ".txt":
        raw = path.read_text(encoding="utf-8")
        return ParsedDoc(text=raw, source=path.name, kind=suffix)
    if suffix == ".pdf":
        return _parse_pdf(path)          # 二进制格式, 不能先 read_text
    raise ValueError(f"不支持的格式: {suffix}")


def _parse_pdf(path: Path) -> ParsedDoc:
    """pdf: 逐页抽文字层, 页与页之间用空行分隔。

    若全部页面都没有文字层 -> 大概率是扫描件, 给出明确提示而不是返回空文本。
    """
    import pdfplumber  # 局部 import: 只有真碰到 pdf 才加载, 启动更快

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if not text.strip():
        raise ValueError("pdf 没有可抽取的文字层(可能是扫描件), 低配版不支持, 需 OCR")
    return ParsedDoc(text=text, source=path.name, kind="pdf")


def parse_dir(root: Path) -> ParseReport:
    """扫描目录下所有受支持格式的文件, 逐个解析。

    单个文件失败只记录, 不中断——知识库里混进一个坏文件是常态。
    """
    report = ParseReport()
    if not root.is_dir():
        report.errors.append(f"{root}: 目录不存在")
        return report
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        try:
            report.docs.append(parse_file(path))
        except Exception as exc:                      # noqa: BLE001 坏文件是常态, 收口成记录
            report.errors.append(f"{path.name}: {exc}")
    return report


if __name__ == "__main__":
    # 自测: 解析本仓库自带的示例文档目录
    demo = Path(__file__).resolve().parent.parent / "sample_docs"
    rep = parse_dir(demo)
    print(f"成功 {len(rep.docs)} 个:")
    for d in rep.docs:
        preview = d.text[:40].replace("\n", " ")
        print(f"  [{d.kind}] {d.source} {len(d.text)} 字符 | {preview}...")
    if rep.errors:
        print(f"失败 {len(rep.errors)} 个:")
        for e in rep.errors:
            print("  ", e)
