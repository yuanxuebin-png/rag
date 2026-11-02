# Git 常用操作笔记

## 基本工作流

改文件后三步走: `git add 文件` 把改动放进暂存区, `git commit -m "说明"` 提交, `git push` 推到远端。
`git status` 随时看当前状态, `git log --oneline` 看一行的提交历史。

## 撤销操作

改乱了还没 add: `git checkout -- 文件名` 丢弃工作区改动(不可恢复, 慎用)。
已经 add 还没 commit: `git reset 文件名` 退出暂存区, 文件内容不丢。
已经 commit 还没 push: `git reset --soft HEAD~1` 撤销提交但保留改动。
已经 push 出去: 不要 reset, 用 `git revert 提交号` 生成一个反向提交, 历史安全。

## 分支

`git switch -c feature-x` 新建并切换分支; 合并回主分支: `git switch main` 后 `git merge feature-x`。
合并冲突时 Git 会在文件里标出 `<<<<<<<` `=======` `>>>>>>>` 三段, 手工改完 `git add` 再 commit。

## 远端与标签

`git remote -v` 查看远端地址; 换地址用 `git remote set-url origin 新地址`。
发布版本打标签: `git tag v1.0` 后 `git push --tags`。
克隆指定分支: `git clone -b 分支名 仓库地址`。

## .gitignore 与大文件

`.gitignore` 每行一个模式, `*.pyc` 忽略所有 pyc, `.venv/` 忽略整个虚拟环境目录, `.env` 必须忽略防止泄露密钥。
已经提交过的文件再加进 .gitignore 不会自动移除, 要 `git rm --cached 文件名` 从索引里摘掉。
单文件超过 100MB 会被 GitHub 直接拒绝, 需要用 Git LFS 或改成网盘存档。
