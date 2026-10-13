# 发布到 GitHub（给你自己用）

本目录已经是一份独立小仓库内容。推荐**单独建一个 GitHub 仓库**，不要把整个 DataFlow-WebUI 私有环境推上去。

## 1. 在 GitHub 新建空仓库

例如仓库名：`cnki-kb-cleaning-pipeline`（Public 或 Private 均可）。

不要勾选 “Add a README”（本地已有）。

## 2. 在本机初始化并推送

在 PowerShell：

```powershell
cd D:\DataFlow-WebUI-main\share\cnki-kb-cleaning-pipeline

# 确认没有密钥
Select-String -Path .\pipeline\*.json -Pattern "sk-" -SimpleMatch

git init
git add .
git status
git commit -m "Initial portable KB text cleaning pipeline for DataFlow-WebUI"
git branch -M main
git remote add origin https://github.com/<你的用户名>/cnki-kb-cleaning-pipeline.git
git push -u origin main
```

若使用 SSH：

```powershell
git remote add origin git@github.com:<你的用户名>/cnki-kb-cleaning-pipeline.git
git push -u origin main
```

## 3. 发布前检查

- [ ] `pipeline/materialized.json` 已被 `.gitignore` 忽略（含你的本机路径）
- [ ] `samples/input.ready.jsonl` 已被忽略
- [ ] JSON 中无 `sk-`、无他人论文原文
- [ ] README 里 Serving / 路径说明清楚

需要我代你执行 `git init` + `gh repo create` + `push` 时，把 **GitHub 用户名** 和仓库名发我，并明确说「可以 push」。
