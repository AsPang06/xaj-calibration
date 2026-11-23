# 发布到 GitHub

本仓库已在本地初始化（分支 `main`）并完成首次提交，**推送**这一步需要你在能访问 github.com
的环境中执行——当前机器到 github.com:443 不可达，我无法代你推送。

下面按“先在网页建空仓库，再本地 push”的顺序操作，HTTPS 与 SSH 二选一即可。

---

## 0. 在 GitHub 上建一个空仓库

1. 打开 <https://github.com/new>
2. Repository name 填 `xaj-calibration`
3. **不要**勾选 “Add a README file”“Add .gitignore”“Choose a license”（保持空仓库，
   否则首推会遇到 `rejected (fetch first)`）
4. Public / Private 按需选择 → Create repository

---

## 1. 方式 A：HTTPS + Personal Access Token

GitHub 已不支持账号密码推送，需要 PAT：

1. 打开 <https://github.com/settings/tokens> → Generate new token (classic)
2. 勾选 `repo` 权限 → 生成后复制（页面关闭后不再显示）
3. 在项目目录执行：

```powershell
cd D:\新安江模型\xaj-calibration
git remote add origin https://github.com/<你的GitHub用户名>/xaj-calibration.git
git push -u origin main
```

提示用户名时填 GitHub 用户名，**密码处粘贴 PAT**（不是登录密码）。

建议启用凭据管理器，避免每次输入：

```powershell
git config --global credential.helper manager
```

---

## 2. 方式 B：SSH（推荐长期使用）

```powershell
ssh-keygen -t ed25519 -C "3391764735@qq.com"      # 一路回车，用默认路径即可
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub  # 复制整行公钥
```

把公钥粘贴到 <https://github.com/settings/keys> → New SSH key，然后：

```powershell
ssh -T git@github.com        # 出现 "Hi <用户名>!" 即配置成功
cd D:\新安江模型\xaj-calibration
git remote add origin git@github.com:<你的GitHub用户名>/xaj-calibration.git
git push -u origin main
```

---

## 3. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `Failed to connect to github.com port 443` | 网络不通。校园网/公司网常需代理：`git config --global http.proxy http://127.0.0.1:<端口>`，取消用 `--unset` |
| `Support for password authentication was removed` | 用了登录密码，改用 PAT 或 SSH |
| `remote origin already exists` | `git remote set-url origin <新地址>` |
| `rejected ... fetch first` | 网页建仓库时勾了 README，先 `git pull --rebase origin main` 再 push |
| 推送很慢/中断 | 换 SSH；或 `git config --global http.postBuffer 524288000` |
| README 图片不显示 | 图用相对路径引用 `outputs/figures/`，确认该目录已提交（`git ls-files outputs/figures`） |

---

## 4. 推送之后

- **About** 建议填写：`三水源新安江模型的参数率定、洪水预报检验与不确定性分析`；
  Topics 建议：`hydrology`、`xinanjiang`、`flood-forecasting`、`calibration`、`python`。
- **打标签**：`git tag -a v1.0.0 -m "首个完整版本" && git push --tags`
- **是否保留 `outputs/`**：目前连同结果一起提交（约 1 MB），好处是克隆后立刻能跑
  `05_verify.py` 且 GitHub 上可直接看结果图。若想只留源码，执行
  `git rm -r --cached outputs`，把 `outputs/` 加进 `.gitignore` 再提交——但此时
  `05_verify.py` 需要先跑完 01~04 才能通过。
- **报告**：`report/新安江模型参数率定报告.docx`（约 0.75 MB）已提交，GitHub 支持在线
  预览 docx；如需 PDF，用 Word/WPS 另存后放在 Release 附件里，比塞进仓库更合适。

---

## 5. 仓库里有什么

- 57 个文件、约 2.25 MB；无密钥、无数据集以外的第三方素材。
- 首次提交信息：`feat: 新安江模型参数率定与洪水预报检验流水线`。
- `.gitignore` 已忽略 `__pycache__`、`.pytest_cache`、`_repro_backup`、`_probe`、
  `.lo_profile` 等本地痕迹。
