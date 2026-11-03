# pocket-rag —— 个人知识库问答(低配多模态 RAG)

把一个文件夹里的 md / txt / pdf 变成可问答的知识库: 检索命中后返回**带编号引用**的答案,
每句话可回溯到来源文件与小节标题; 库里没有的内容**明确拒答**, 不编造。

LangChain 1.x + DeepSeek, 纯 Python 3.13 实现。不依赖向量库与重排模型,
各层结构简单、便于完整审读, 定位是呈现 RAG 的核心工程取舍。

## 实测结果(全部真跑, 留档可查)

| 指标 | 数字 | 说明 |
|---|---|---|
| 检索命中率 | **12/12** | 12 个库内问题的金标小节全部进入 top-4 |
| 拒答判定正确率 | **15/15** | 3 个库外问题全部拒答, 且无误拒 |
| 答案关键词命中 | **12/12** | 每题一次真实模型调用, 答案含关键事实 |

评测提供两种模式: `--offline`(仅检索与拒答判定, 无模型调用, 秒级完成)
与全量模式(含真实模型调用)。明细留档: `docs/eval_result.md`。

## 核心设计

```
sample_docs/ (md/txt/pdf)
      │  parse.py     多格式解析: md/txt 直接读, pdf 抽文字层(扫描件明确报错不硬解析)
      ▼
  父子块 (chunk.py)   子块≈200字用于检索定位; 命中后返回所属父块(整个小节)给模型,
      │               即「小块定位, 大块作答」
      ▼
  检索 (retrieve.py)  BM25(jieba)永远可用; 配了 embedding key 才启用向量通道;
      │               两路结果用 RRF 融合(只看排名, 不比较不可通约的分数);
      │               BM25 最高分低于阈值 -> 拒答
      ▼
  答案 (answer.py)    只准基于给定材料作答, 每句结论标 [1][2], 来源清单回显
```

核心取舍:

1. **BM25 是底线, 向量是增强项**。未配置 embedding key 时自动退化为纯 BM25,
   检索能力保持完整——本仓库的评测数字即由纯 BM25 跑出。
2. **拒答优先于答错**。拒答阈值不使用 RRF 分数(其仅有排序意义, 量级 0.0x),
   而基于 BM25 原始分。实测发现: 不过滤停用词时, 「怎么做红烧肉」可依靠"怎么"
   一词获得 4.56 的高分击穿阈值——库外问题的拦截需要停用词与阈值双重保障。
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

# HTTP 查询接口(供 patch-agent 的 query_knowledge 工具调用)
python -m pocket_rag.api            # 默认 127.0.0.1:8765, POST /query + GET /health

# 评测: 先离线(秒级), 再全量(真实调用)
python -m pocket_rag.evals --offline
python -m pocket_rag.evals
```

将 `pocket_rag/cli.py` 中的 `docs_dir` 指向其他文档目录, 即可作为个人知识库使用。

## 目录结构

```
pocket-rag/
├── pocket_rag/
│   ├── parse.py        # 多格式解析(坏文件记录跳过, 不拖垮索引)
│   ├── chunk.py        # 父子块切分(滑窗子块 + 段落续切长父块)
│   ├── retrieve.py     # 混合检索 + RRF + 拒答
│   ├── answer.py       # 带引用编号的答案生成
│   ├── api.py          # HTTP 查询接口(标准库实现, 供外部系统联动调用)
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
