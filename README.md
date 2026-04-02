
# pmflow

抖音舆情分析工作台 · 本地离线版

> 将抖音导出的 CSV 数据一键写入本地 SQLite，自动生成三模块舆情报告，提供 Web 分析界面。

---

## 快速部署

### 环境要求

- macOS / Linux
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
```

启动后访问：

| 服务 | 地址 |
|---|---|
| 分析界面 | http://localhost:8501 |
| API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

---

## 项目结构

```
pm-flow/
├── api/                  # FastAPI 后端
│   └── server.py
├── ingest/               # CSV → SQLite 导入模块
│   └── douyin_csv_to_sqlite.py
├── pipeline/             # 报告生成管线
│   ├── report.py
│   └── retrieve.py
├── ui/                   # Streamlit 前端
│   └── app.py
├── raw/                  # 放入原始 CSV（不上传 git）
├── data/                 # SQLite 数据库（不上传 git）
├── outputs/              # 生成的报告（不上传 git）
├── logs/                 # 运行日志（不上传 git）
├── setup.sh              # 首次初始化
├── start.sh              # 启动服务
├── stop.sh               # 停止服务
└── requirements.txt
```

---

## 使用流程

1. **导入数据** — 将抖音导出的 CSV 放入 `raw/`，在 UI「导入数据」页一键写入
2. **生成报告** — 在「生成报告」页选择关键词，自动生成 Markdown 报告
3. **数据浏览** — 在「数据浏览」页查看原始 posts / comments 数据

---

## 停止服务

```bash
bash stop.sh
```
