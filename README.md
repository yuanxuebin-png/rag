# pocket-rag —— 个人知识库问答(低配多模态 RAG)

把一个文件夹里的 md / txt / pdf 变成可问答的知识库: 检索命中后返回**带编号引用**的答案,
每句话可回溯到来源文件与小节标题; 库里没有的内容**明确拒答**, 不编造。

LangChain 1.x + DeepSeek, 纯 Python 3.13。没有向量库、没有重排模型、没有框架魔法——
每一层都可以在 10 分钟内读完源码, 这是"低配版"的定位: **把 RAG 的核心取舍讲清楚**。

## 实测结果(全部真跑, 留档可查)

| 指标 | 数字 | 说明 |
|---|---|---|
| 检索命中率 | **12/12** | 12 个库内问题的金标小节全部进入 top-4 |
| 拒答判定正确率 | **15/15** | 3 个库外问题(天气/红烧肉/世界杯)全部拒答, 且无误拒 |
| 答案关键词命中 | **12/12** | 每题一次真实模型调用, 答案含关键事实 |

评测脚本: `python -m pocket_rag.evals --offline`(秒级, 不花钱) / 全量(含模型调用)。
明细留档: `docs/eval_result.md`。

## 核心设计

```
sample_docs/ (md/txt/pdf)
      │  parse.py     多格式解析: md/txt 直接读, pdf 抽文字层(扫描件明确报错不硬解析)
      ▼
  父子块 (chunk.py)   子块≈200字用于检索定位; 命中后返回所属父块(整个小节)给模型
      │               ——「小块定位, 大块作答」, 父子块的全部意义
      ▼
  检索 (retrieve.py)  BM25(jieba)永远可用; 配了 embedding key 才启用向量通道;
      │               两路结果用 RRF 融合(只看排名, 不比较不可通约的分数);
      │               BM25 最高分低于阈值 -> 拒答
      ▼
  答案 (answer.py)    只准基于给定材料作答, 每句结论标 [1][2], 来源清单回显
```

三个值得讲的取舍:

1. **BM25 是底线, 向量是加分项**。没有 embedding key 时自动退化为纯 BM25,
   功能不残废——本仓库的评测数字就是纯 BM25 跑出来的。
2. **拒答比答错严重**。拒答阈值不用 RRF 分(它只有排名意义, 0.0x 量级),
   用 BM25 原始分。实测还发现: 不滤停用词时, 「怎么做红烧肉」靠"怎么"二字
   蹭到 4.56 的高分击穿阈值——库外问题必须靠停用词+阈值双保险。
3. **引用编号是硬约束**。提示词强制每个结论带 [n], 用户可回溯核对;
   检索拒答时根本不调模型, 这是幻觉的第二道闸。

## 快速开始

```bash
# 依赖: python 3.13+, langchain 1.x, rank-bm25, jieba, pdfplumber
cp .env.example .env        # 填 DeepSeek key; SiliconFlow key 可选(启用向量通道)

# 生成示例 PDF(可选, fpdf2 + 系统黑体)
python sample_docs/make_sample_pdf.py

# 问答(交互模式 / 单问模式)
python -m pocket_rag.cli
python -m pocket_rag.cli "DeepSeek 上 max_tokens 怎么写才生效"

# 评测: 先离线(秒级), 再全量(真实调用)
python -m pocket_rag.evals --offline
python -m pocket_rag.evals
```

把 `sample_docs` 换成你自己的文档目录即可变成个人知识库(cli.py 里的 `docs_dir`)。

## 目录结构

```
pocket-rag/
├── pocket_rag/
│   ├── parse.py        # 多格式解析(坏文件记录跳过, 不拖垮索引)
│   ├── chunk.py        # 父子块切分(滑窗子块 + 段落续切长父块)
│   ├── retrieve.py     # 混合检索 + RRF + 拒答
│   ├── answer.py       # 带引用编号的答案生成
│   ├── evals.py        # 15 条评测(三层判定, 支持 --offline)
│   └── cli.py          # 交互/单问命令行入口
├── sample_docs/        # 示例知识库(5 篇笔记 + 1 个脚本生成的 PDF)
└── docs/eval_result.md # 评测留档(自动生成)
```

## Roadmap

- [x] 多格式解析(md/txt/pdf 文字层)
- [x] 父子块切分
- [x] BM25+jieba 检索 + 可选向量 RRF 融合 + 拒答
- [x] 带溯源引用的答案生成
- [x] 15 条三层评测(离线/在线双模式)
- [ ] v2: 扫描件 OCR(rapidocr)接入 parse 的 pdf 通道
- [ ] v2: 查询改写(同义扩展)提升 BM25 召回
