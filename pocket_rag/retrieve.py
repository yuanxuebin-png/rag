"""混合检索: BM25(jieba 分词)为主, 可选向量召回, RRF 融合, 分数不够就拒答。

低配版的关键决策
----------------
- **BM25 永远可用**: 纯本地、零额外依赖、零 API 费用, 是这条链路的底线
- **向量召回是可选加分项**: 只有环境里配了 embedding 服务(SILICONFLOW_API_KEY
  或 OPENAI 兼容的 embedding 接口)才启用; 没配就自动退化成纯 BM25, 功能不残废
- **RRF(Reciprocal Rank Fusion)融合**: 只看两边各自排名, 不比较不可通约的
  分数——BM25 分和余弦相似度量纲不同, 直接加权是常见错误
- **拒答**: 最高分低于阈值说明知识库里没有相关内容, 直接说"不知道"。
  RAG 系统的第一美德是不知道就说不知道, 编造比答不上严重得多
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi

from pocket_rag.chunk import Child, Parent

REFUSE_THRESHOLD = 2.5    # BM25 原始最高分低于此值 -> 拒答(评测集上调参确定)
RRF_K = 60                # RRF 常数, 论文默认值


@dataclass
class Hit:
    """一条检索命中: 已经从子块升到父块。"""

    parent: Parent
    score: float        # RRF 融合分(或纯 BM25 的排名分)
    matched_child: str  # 命中的子块原文, 调试/展示用


def tokenize(text: str) -> list[str]:
    """jieba 分词 + 小写 + 去空白, BM25 与查询两侧必须用同一个函数。"""
    return [w.lower() for w in jieba.lcut(text) if w.strip()]


class Retriever:
    """检索器: build 一次, query 多次。"""

    def __init__(self, parents: list[Parent], children: list[Child]) -> None:
        self.parents = parents
        self.children = children
        self._pid2parent = {p.pid: p for p in parents}

        # ---- BM25 通道(永远启用) ----
        self._bm25 = BM25Okapi([tokenize(c.text) for c in children])

        # ---- 向量通道(可选, 环境没配就关) ----
        self._embed = self._make_embedder()
        self._child_vecs = None
        if self._embed is not None:
            self._child_vecs = [self._embed(c.text) for c in children]

    # ------------------------------------------------------------------
    def _make_embedder(self):
        """探测环境里可用的 embedding 服务, 没有就返回 None(纯 BM25 模式)。

        优先 SiliconFlow(BGE 系列, 国内直连), 其次任意 OpenAI 兼容接口。
        """
        key = os.environ.get("SILICONFLOW_API_KEY")
        if not key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        client = OpenAI(api_key=key, base_url="https://api.siliconflow.cn/v1")

        def embed(text: str) -> list[float]:
            resp = client.embeddings.create(
                model="BAAI/bge-m3", input=text[:512])
            return resp.data[0].embedding

        return embed

    # ------------------------------------------------------------------
    def _bm25_ranks(self, query: str, top_n: int) -> list[tuple[int, float]]:
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(self.children)),
                       key=lambda i: scores[i], reverse=True)[:top_n]
        return [(i, scores[i]) for i in order if scores[i] > 0]

    def _vec_ranks(self, query: str, top_n: int) -> list[tuple[int, float]]:
        if self._embed is None:
            return []
        import numpy as np

        qv = np.array(self._embed(query))
        cvs = np.array(self._child_vecs)
        sims = cvs @ qv / (np.linalg.norm(cvs, axis=1) * np.linalg.norm(qv) + 1e-9)
        order = np.argsort(-sims)[:top_n]
        return [(int(i), float(sims[i])) for i in order]

    @staticmethod
    def _rrf_fuse(rank_lists: list[list[int]], top_n: int) -> dict[int, float]:
        """RRF: 每个通道给候选贡献 1/(k+排名), 只用排名不用原始分。"""
        fused: dict[int, float] = {}
        for ranks in rank_lists:
            for rank, idx in enumerate(ranks):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        return dict(sorted(fused.items(), key=lambda kv: -kv[1])[:top_n])

    # ------------------------------------------------------------------
    def query(self, question: str, top_k: int = 4) -> list[Hit] | None:
        """检索入口。返回 None 表示该拒答(知识库里没有相关内容)。

        流程: 两个通道各取 top10 子块 -> RRF 融合 -> 分数门槛 -> 子块升父块去重。
        """
        bm = self._bm25_ranks(question, 10)
        vc = self._vec_ranks(question, 10)
        rank_lists = [[i for i, _ in bm]] + [[i for i, _ in vc]]
        fused = self._rrf_fuse(rank_lists, top_n=20)

        # 拒答判据用 BM25 原始分: RRF 分只有 0.0x 量级、且只反映排名,
        # 拿它设阈值等于没设; BM25 分才反映「词项到底匹配上没有」。
        if not bm or bm[0][1] < REFUSE_THRESHOLD:
            return None                                  # 拒答

        hits: list[Hit] = []
        seen_pids: set[str] = set()
        for idx, score in fused.items():
            child = self.children[idx]
            if child.parent_pid in seen_pids:
                continue                                 # 同一父块只取最高分子块
            seen_pids.add(child.parent_pid)
            hits.append(Hit(parent=self._pid2parent[child.parent_pid],
                            score=round(score, 4),
                            matched_child=child.text))
            if len(hits) >= top_k:
                break
        return hits


if __name__ == "__main__":
    # 自测: 索引示例文档, 抽查几个问题的检索结果(不调任何 API, 纯本地)
    from pathlib import Path
    from pocket_rag.parse import parse_dir
    from pocket_rag.chunk import chunk_all

    demo = Path(__file__).resolve().parent.parent / "sample_docs"
    rep = parse_dir(demo)
    parents, children = chunk_all(rep.docs)
    r = Retriever(parents, children)

    for q in ["怎么撤销已经 push 的提交", "DeepSeek 上 max_tokens 怎么写才生效",
              "北京今天天气怎么样"]:
        hits = r.query(q)
        print(f"\nQ: {q}")
        if hits is None:
            print("  -> 拒答(库内无相关内容)")
        else:
            for h in hits:
                print(f"  [{h.score}] {h.parent.pid}")
