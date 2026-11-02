# Python 虚拟环境与 pip 笔记

## 为什么要用虚拟环境

虚拟环境(virtual environment)把一个项目的依赖和系统 Python 隔离开。
不同项目可能需要不同版本的同一个库, 直接装进全局会互相覆盖。
每个项目一个 `.venv` 目录, 激活后 `python` 和 `pip` 都指向这个私有副本。

## 创建与激活

用标准库 venv 模块创建: `python -m venv .venv`。
Windows 下激活脚本在 `.venv\Scripts\activate`, Linux/macOS 在 `.venv/bin/activate`。
不激活也能用: 直接调用 `.venv\Scripts\python.exe` 全路径效果相同, 脚本里推荐这种写法。

## requirements.txt 的正确姿势

`pip freeze > requirements.txt` 会把间接依赖全部钉死, 适合锁版本。
更推荐只写直接依赖, 交由 `pip install -r requirements.txt` 自动解析版本。
安装指定版本用 `pip install "langchain>=1.4,<2"` 这种范围写法。

## 常见坑

pip 装了包但 import 报错, 九成是装到了另一个解释器里。
排查方法: `python -m pip list` 看当前解释器到底装了什么;
`python -c "import sys; print(sys.executable)"` 确认用的是哪个 Python。
不要用 `pip install` 裸命令, 一律 `python -m pip install`, 保证装进当前解释器。

## 卸载与清理

`pip uninstall 包名` 只删包不删依赖; 想彻底重来直接删掉 `.venv` 目录重建, 成本极低。
缓存清理: `pip cache purge`。国内网络慢可加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 走清华镜像。
