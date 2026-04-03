# competitive-intel

竞品分析数据工作台 · 本地离线版

> 将多平台导出的 CSV 数据一键写入本地 SQLite，自动生成三模块舆情报告，提供 Web 分析界面。

---

## 快速部署

### 环境要求

- macOS / Linux / WSL2
- Python 3.10+

### 三步启动

```bash  
# 1. clone 项目  
git clone https://github.com/你的用户名/pm-flow.git  
cd pm-flow  

# 2. 初始化（创建虚拟环境 + 安装依赖）  
bash setup.sh  

# 3. 放入数据，启动服务  
# 把 search_contents_*.csv 和 search_comments_*.csv 放入 raw/ 目录  
bash start.sh  
启动后访问：

服务	地址	说明
Web UI	http://localhost:8501	Streamlit 分析界面
API	http://localhost:8000	FastAPI 后端
API 文档	http://localhost:8000/docs	OpenAPI 交互式文档
项目结构
bash
pm-flow/
├── api/                  # FastAPI 后端
│   └── server.py         # 爬取、导入、查询 API
├── ingest/               # CSV → SQLite 导入
│   └── csv_to_sqlite.py  # 通用多平台导入脚本
├── pipeline/             # 报告生成
│   ├── report.py         # 报告生成逻辑
│   └── retrieve.py       # 数据检索
├── ui/                   # Streamlit 前端
│   └── app.py            # Web 界面
├── raw/                  # 放入原始 CSV（git 忽略）
├── data/                 # SQLite 数据库（git 忽略）
│   └── pmflow.db         # 默认数据库位置
├── outputs/              # 生成的报告（git 忽略）
├── logs/                 # 运行日志（git 忽略）
├── setup.sh              # 初始化脚本
├── start.sh              # 启动脚本
├── stop.sh               # 停止脚本
└── requirements.txt
数据流说明
bash
平台导出 CSV
    ↓
放入 raw/ 目录
    ↓
UI 或 API 点击「导入」
    ↓
csv_to_sqlite.py 自动转换
    ↓
数据写入 data/pmflow.db
    ↓
UI 读取数据库生成报告
支持的平台
平台	CSV 文件名	说明
抖音	search_contents_*.csv	douyin 平台
小红书	search_contents_*.csv	xhs 平台
B站	search_contents_*.csv	bili 平台
快手	search_contents_*.csv	ks 平台
微博	search_contents_*.csv	wb 平台
贴吧	search_contents_*.csv	tieba 平台
知乎	search_contents_*.csv	zhihu 平台
注意：导入时需要指定平台标识，脚本会根据平台自动识别 CSV 列名。

常用操作
在 UI 中导入数据
启动服务：bash start.sh
打开 http://localhost:8501
在「导入数据」页：
选择 raw/ 中的 CSV 文件
指定平台（douyin/bili/xhs 等）
点击「导入」
命令行导入（高级用户）
bash
# 导入 B站 数据
python ingest/csv_to_sqlite.py \
  --contents raw/search_contents_2026-04-03.csv \
  --comments raw/search_comments_2026-04-03.csv \
  --platform bili \
  --db data/pmflow.db

# 导入小红书数据
python ingest/csv_to_sqlite.py \
  --contents raw/search_contents_2026-04-03.csv \
  --comments raw/search_comments_2026-04-03.csv \
  --platform xhs \
  --db data/pmflow.db
停止服务
bash
bash stop.sh
常见问题
Q1: 导入后 posts 为 0，comments 有数据
A: 说明 posts CSV 的主键列名没被识别。

排查步骤：

bash
# 查看 CSV 的列名
head -1 raw/search_contents_*.csv | cat -A

# 查看前几行数据
head -3 raw/search_contents_*.csv
解决办法：

打开 ingest/csv_to_sqlite.py，找到 PLATFORM_FIELD_MAP[您的平台]["post_id"]
查看列表中的字段名是否包含了 CSV 实际的列名（如 video_id、bvid、aweme_id 等）
若缺少，添加到列表中，保存后重新导入
示例（B站为例，如果用了 video_id）：

python
"bili": {
    "post_id": ["video_id", "bvid", "id"],  # 确保包含 video_id
    ...
}
Q2: 报错 name 'req' is not defined
A: server.py 中的函数参数传递有问题。确保调用导入函数时：

python
# ✓ 正确做法
ingest_posts(conn, str(contents), platform=platform_short)

# ✗ 错误做法
ingest_posts(conn, str(contents), platform=req.platform)  # req 未定义
Q3: 导入文件找不到
A: 检查文件路径和权限

bash
# 确认 raw/ 目录存在且有 CSV 文件
ls -lh raw/

# 确认数据库目录存在
mkdir -p data/
Q4: 数据写到不同的 DB 文件
A: 保证统一使用同一 DB 路径，建议始终用 data/pmflow.db

bash
# 在 server.py、setup.sh、start.sh 中统一指定
DB_PATH="data/pmflow.db"
Q5: CSV 导入后数据为空或只有空行
A:

检查 CSV 文件是否损坏或编码有问题
用文本编辑器打开，确认有实际数据行（不只是表头）
若有中文乱码，尝试转换为 UTF-8 编码
Q6: 如何查看数据库中的数据？
A: 使用 sqlite3 命令行

bash
# 查看 posts 数量
sqlite3 data/pmflow.db "SELECT COUNT(*) FROM posts;"

# 查看 comments 数量
sqlite3 data/pmflow.db "SELECT COUNT(*) FROM comments;"

# 查看某关键词的 posts
sqlite3 data/pmflow.db "SELECT post_id, title, created_at FROM posts WHERE keyword='你的关键词' LIMIT 5;"
开发与协作
本地开发流程
bash
# 1. 基于 develop 分支创建功能分支（不影响 main）
git checkout develop
git checkout -b feature/您的功能名

# 2. 开发完成后提交
git add .
git commit -m "feat: 您的改动说明"

# 3. 推送到远程
git push origin feature/您的功能名

# 4. 在 GitHub 上创建 Pull Request，合并到 develop 分支
分支说明
分支	用途	可否直接修改
main	稳定发布版本	✗ 需要通过 PR 合并
develop	开发分支	✓ 日常开发在此分支
feature/*	功能分支	✓ 完成后 PR 合并到 develop
运行单元测试（如有）
bash
pytest tests/ -v
日志与调试
运行日志：logs/ 目录
API 调试：访问 http://localhost:8000/docs（Swagger UI）
Streamlit 调试：终端会输出 Streamlit 日志
启用详细日志
在 server.py 中设置：

python
import logging
logging.basicConfig(level=logging.DEBUG)
停止与清理
bash
# 停止服务
bash stop.sh

# 清理临时文件与缓存
rm -rf .pytest_cache __pycache__ .streamlit/
环境变量配置（可选）
若需要自定义路径，在 .env 文件中设置：

env
RAW_DIR=raw/
DB_PATH=data/pmflow.db
LOG_DIR=logs/
在 server.py 中读取：

python
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv('DB_PATH', 'data/pmflow.db')
RAW_DIR = os.getenv('RAW_DIR', 'raw/')
常见改动清单
需求	位置	说明
添加新平台支持	ingest/csv_to_sqlite.py - PLATFORM_FIELD_MAP	在字典中添加平台及列名映射
修改 UI 界面	ui/app.py	Streamlit 代码
添加新的 API 接口	api/server.py	FastAPI 路由
修改报告模板	pipeline/report.py	Markdown 报告生成逻辑
修改数据库架构	ingest/csv_to_sqlite.py - ensure_schema()	创建表和索引
性能优化建议
若 CSV 文件很大（>1GB），考虑分批导入
定期备份 data/pmflow.db
为常用查询添加数据库索引
许可证
MIT License

更新日志
v1.1.0（2026-04-03）
✨ 完成多平台 CSV 导入器（支持 7 个平台）
🐛 修复 B站 video_id 字段识别问题
📝 更新 README 与文档
🔧 改进错误处理与日志记录
v1.0.0（初始版本）
✓ 基础导入与 UI 框架
✓ FastAPI 后端
✓ Streamlit 前端
反馈与支持
发现 Bug：在 GitHub 提 Issue
功能建议：欢迎 PR 或讨论
问题咨询：通过 GitHub Discussions