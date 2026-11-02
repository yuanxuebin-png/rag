"""生成示例 PDF: sample_docs/git-flow.pdf。

作用有二:
1. 给 parse.py 的 pdf 通道提供一个真实的解析对象(可复现, 不依赖外部文件)
2. 证明「同一套解析入口能吃下 md/txt/pdf 三种格式」——多格式解析是本项目的卖点

用 fpdf2 + Windows 自带黑体(simhei.ttf)生成中文 PDF; fpdf2 默认拉丁字体写不了中文,
必须注册 TTF。运行: python sample_docs/make_sample_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

SECTIONS = [
    ("Git 分支管理流程", [
        "本文用于演示 pocket-rag 的 PDF 解析通道, 内容本身是一份简明的分支管理流程。",
        "主分支 main 保持随时可发布状态, 一切开发都在特性分支上进行。",
    ]),
    ("一、特性分支流程", [
        "第一步, 从 main 拉出新分支: git switch -c feature-login。",
        "第二步, 在特性分支上提交代码, 每个提交只做一件事, 说明写清楚为什么改。",
        "第三步, 开发完成后把 main 的最新代码合进来, 先在本地解决冲突再推远端。",
        "第四步, 发起合并请求, 请至少一名同事审查, 审查通过后合并并删除特性分支。",
    ]),
    ("二、发布与热修", [
        "发布时从 main 打标签, 例如 v1.2, 标签一旦打出不再移动。",
        "线上出 bug 时从对应标签拉 hotfix 分支, 修完合并回 main 并重新打补丁版本标签。",
        "禁止直接在 main 上改代码, 禁止 force push 共享分支。",
    ]),
]


def main() -> None:
    here = Path(__file__).resolve().parent
    out = here / "git-flow.pdf"

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("simhei", "", str(Path("C:/Windows/Fonts/simhei.ttf")))
    pdf.set_font("simhei", size=14)
    for title, paras in SECTIONS:
        pdf.set_font_size(14)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font_size(11)
        for p in paras:
            pdf.multi_cell(0, 7, p, new_x="LMARGIN")   # 默认光标停在右边缘, 必须拉回
        pdf.ln(4)
    pdf.output(out)
    print(f"生成: {out} ({out.stat().st_size} 字节)")


if __name__ == "__main__":
    main()
