"""HTTP 查询接口 —— 双项目联动的「知识底座」出口。

为什么用标准库 http.server 而不是 FastAPI
------------------------------------------
本项目的定位是低配、零额外依赖的本地服务。查询接口只有「收一个问题、
返回一个 JSON」一件事, 标准库完全够用; 引入 FastAPI 反而多一层
「依赖没装跑不起来」的故障面。工程上正确的选型是按需选, 不是按流行选。

接口
----
POST /query   body: {"question": "..."}   -> {"answer", "sources", "refused", "n_hits"}
GET  /health                             -> {"status": "ok"}  (联动方探活用)

用法
----
  python -m pocket_rag.api                    # 默认 127.0.0.1:8765
  python -m pocket_rag.api 8900               # 指定端口

调用方(patch-agent 的 query_knowledge 工具)用 /health 探活, 用 /query 提问。
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pocket_rag.answer import answer_question
from pocket_rag.cli import build_retriever
from pocket_rag.retrieve import Retriever

_RETRIEVER: Retriever | None = None     # 进程启动时构建一次, 之后复用


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:              # 探活
        if self.path == "/health":
            self._send(200, {"status": "ok", "docs_indexed": _RETRIEVER is not None})
        else:
            self._send(404, {"error": "only GET /health"})

    def do_POST(self) -> None:             # 提问
        if self.path != "/query":
            self._send(404, {"error": "only POST /query"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            question = json.loads(self.rfile.read(length))["question"].strip()
        except Exception:
            self._send(400, {"error": "body 必须是 {\"question\": \"...\"}"})
            return
        if not question:
            self._send(400, {"error": "question 不能为空"})
            return

        hits = _RETRIEVER.query(question)
        ans = answer_question(question, hits)
        self._send(200, {
            "answer": ans.text,
            "sources": ans.sources,
            "refused": ans.refused,
            "n_hits": ans.n_hits,
        })

    def log_message(self, fmt: str, *args) -> None:
        """静默默认访问日志(每次提问一行太吵), 真错误走异常路径。"""


def main() -> None:
    global _RETRIEVER
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    docs_dir = Path(__file__).resolve().parent.parent / "sample_docs"
    _RETRIEVER = build_retriever(docs_dir)          # 索引只建一次
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"知识库 API 就绪: http://127.0.0.1:{port}  (POST /query, GET /health)")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
