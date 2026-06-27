# IBS Fighter

一个本地运行的 IBS 日常追踪工具，用 SQLite 保存数据，当前覆盖：

- 排便：时间、布里斯托 1-7 级、地点、急迫感、颜色、备注
- 饮食：时间、餐别、地点历史下拉、常用餐复刻、历史快捷填充、照片、文字描述、饭后反应、备注
- 药物登记：药物名称、成分、类型、固定单位
- 用药：时间、勾选一个或多个已登记药物、分别填写数量，单位从药物登记自动带出、服用时间关系、备注
- 运动：时间、常用活动快捷填充、活动文本、时长、强度、备注
- 体重：时间、体重、测量条件、备注
- 痔疮：时间、是否流血、备注，用于轻量监控
- 今日检查：排便、三餐、用药、运动和体重是否已记录，帮助发现漏记
- 报表：按分类查看排便、用药和体重，支持 7 天和 30 天周期；排便报表以 Bristol 4-5 为安全区
- AI 分析：饮食照片/文字识别辅助填写，报表页可手动触发 7/30 天 AI 复盘

## 版本更新日志（测试版）

这个日志先按产品迭代节奏记录，不等同于正式 release tag。当前节奏是：先保证记录和部署稳定，再减少手机端摩擦，最后逐步把报表从“展示数据”推进到“监控稳定性”。

### v0.9 - OpenAI 统一 AI 分析接入（2026-06-27）

- 新增统一 AI provider 层，文字、图片和结构化 JSON 输出先统一走 OpenAI Responses API。
- 保留饮食 AI 识别：照片和文字只用于当次识别，用户仍需手动点击“应用到文字描述”。
- 新增常用餐模板：AI 识别或手动填写后可保存为常用餐，后续一键复刻到饮食表单。
- 新增报表 AI 复盘：报表页手动点击 `AI 复盘`，基于当前 7/30 天报表生成稳定信号、注意信号、可能关联和下次记录重点。
- 新增 `ai_analysis_runs` 追溯表：保存模型、功能类型、输入摘要 hash、输出 JSON、错误和采纳状态；不保存图片 base64、API key 或完整 prompt。
- AI 输出统一定位为记录辅助和趋势观察，不做诊断、处方或治疗建议。

### v0.8 - 稳定性监控与轻量健康记录（2026-06-24）

- 新增体重记录：支持记录时间、体重、测量条件和备注，并在报表中查看 7/30 天趋势。
- 简化体重表单：保留真正高频使用的字段，降低手机录入成本。
- 新增痔疮轻量记录：记录是否流血和备注，用于和排便状态一起观察。
- 移除“异常复盘卡”demo：该方向信息密度高但实际使用负担大。
- 新增安全率 p-chart：跟踪过去 7/30 天 Bristol 4-5 占比，回答“整体安全率有没有变稳定”。
- 新增异常间隔 g-chart：跟踪两次非安全排便之间隔了几天、几次安全排便，回答“稳定期有没有变长”。

### v0.7 - Google Drive 备份与图片体积控制（2026-05-30）

- 新增 Google Drive 备份同步流程，线上数据库和上传图片可以打包为 zip 备份。
- 把备份入口放到设置页，使用当前 Google 登录 session 和 CSRF token 触发。
- 备份改为 OAuth 授权优先，避免 Service Account key 被组织策略禁用的问题。
- 新增历史备份导入脚本，本地分析线上数据时不会覆盖本地开发数据库。
- 上传饮食照片统一转成 JPEG 并压缩到约 500KB 以内，控制 Render 磁盘和 Drive 备份增长。

### v0.6 - 排便报表从列表走向控制图（2026-05-27）

- 新增 Bristol 控制图：把 Bristol 4-5 作为安全区，越界点自动标记。
- 简化报表布局：取消占页面但洞察较弱的每日趋势，把重点放在分布、控制图和关注日期。
- 布里斯托分布改为竖向柱状图，形态分布改为文字总结。

### v0.5 - 手机端可用性与跨时区记录（2026-05-25）

- Google 登录 cookie 默认保留 360 天，关闭手机或电脑浏览器后不需要频繁重新登录。
- 改善手机自适应布局，修复小屏下控件宽度和底部导航遮挡问题。
- 修复移动端输入框聚焦时自动放大页面的问题。
- 新增时区感知记录：保存当地显示时间、IANA 时区和 UTC 时间，适配 PNG、所罗门群岛和后续出差场景。

### v0.4 - 公网部署与 Google 登录（2026-05-24）

- 从本地 `http.server` 迁移到 Flask + Gunicorn，支持 Render Web Service 部署。
- 新增 Google OAuth 登录，只允许白名单邮箱访问。
- 新增 `/healthz` 健康检查，方便 Render 部署后验证服务状态。
- 线上主库放 Render persistent disk，Google Drive 作为备份副本。

### v0.3 - OpenAI 饮食识别测试（2026-05-20）

- 新增饮食照片/文字识别测试模块，用于辅助填写食物描述。
- 增加证书依赖处理，降低 macOS 本地调用 OpenAI API 的失败率。

### v0.2 - 模块化与报表基础（2026-05-17 至 2026-05-19）

- 初版完成排便、饮食、药物、用药和运动记录。
- 新增分类用药报表。
- 重构项目结构，把数据库、模型、CRUD、上传、报表和服务入口拆开，方便后续部署和维护。

## 运行

仅在这台电脑上使用：

```bash
python3 -m pip install -r requirements.txt
python3 IBS_Fighter.py
```

打开：

```text
http://127.0.0.1:8765
```

同一 Wi-Fi 下用手机访问：

```bash
./start.sh
```

然后在手机浏览器打开：

```text
http://你的Mac局域网IP:8765
```

公网版本需要 Google 登录。没有配置 Google OAuth 时，本地开发可以临时使用：

```bash
IBS_FIGHTER_AUTH_REQUIRED=0 python3 IBS_Fighter.py
```

使用 `./start.sh` 会让同一局域网里的设备可以访问，请只在可信 Wi-Fi 下使用。

当前定位是本地个人版。一周试用稳定后发布到 GitHub 的仍然只是代码和说明，不包含你的本地数据库、照片或 Excel 原始记录。

数据库文件会自动创建在：

```text
data/ibs_fighter.sqlite3
```

饮食照片会保存在：

```text
uploads/
```

上传的饮食照片会在服务端统一转成 JPEG，并压缩到约 500KB 以内，避免 iPhone 原图长期占满 Render 磁盘和 Google Drive 备份空间。

已有历史照片可以就地重压缩，文件名保持不变：

```bash
python3 scripts/recompress_uploads.py
```

## 公网部署

当前部署目标是 Render Web Service + persistent disk：

```text
build command: pip install -r requirements.txt
start command: gunicorn ibs_fighter.wsgi:app --bind 0.0.0.0:$PORT --timeout 120
disk mount: /var/data
```

`--timeout 120` 用于避免 AI 复盘请求超过 Gunicorn 默认 30 秒后被 Render 显示为 502。

线上数据目录：

```text
IBS_FIGHTER_DATA_DIR=/var/data/data
IBS_FIGHTER_UPLOADS_DIR=/var/data/uploads
```

Google 登录只允许 `GOOGLE_ALLOWED_EMAILS` 里的账号进入。Google Drive 只作为备份副本，不作为 SQLite 主库；备份授权使用 Google OAuth，不需要 Service Account JSON key。详细步骤见 `docs/render-deploy.md`。

登录态使用安全的 HttpOnly cookie。默认 `IBS_FIGHTER_SESSION_DAYS=360`，
所以手机或电脑关闭浏览器后不需要频繁重新登录；主动点击页面上的“退出”仍会立即清除登录态。

### 线上备份到本地分析

Render 线上主库位于 persistent disk，例如：

```text
/var/data/data/ibs_fighter.sqlite3
```

设置页先点击 `连接 Google Drive 备份` 完成授权，然后 `备份到 Google Drive`
会把线上数据库和上传图片打包到 Google Drive。
本地读取线上记录时，不覆盖 `data/ibs_fighter.sqlite3`，而是导入到
`data/render_backups/`：

```bash
python3 scripts/sync_render_backup.py
sqlite3 "$(cat data/render_backups/latest_db_path.txt)" \
  "SELECT date(occurred_at), bristol_type, notes FROM bowel_movements ORDER BY occurred_at DESC LIMIT 5;"
```

如果备份 zip 已经通过 Google Drive Desktop 同步到本机，也可以直接导入：

```bash
python3 scripts/sync_render_backup.py --backup-zip "/path/to/ibs-fighter-backup-YYYYMMDDTHHMMSSZ.zip"
```

## 时区

记录表单仍然按你设备当前的当地时间填写。前端会自动提交浏览器系统时区，后端同时保存：

- 当地显示时间，例如 `2026-05-25T09:30`
- IANA 时区，例如 `Pacific/Guadalcanal`
- 统一 UTC 时间，例如 `2026-05-24T22:30:00Z`

已有历史记录按 PNG 时区 `Pacific/Port_Moresby` 回填；之后在所罗门或其他地区出差时，会按设备系统时区转换。

## AI 分析能力

OpenAI API key 保存在本机 `.env` 或 Render secret env，不能提交到 GitHub：

```text
OPENAI_API_KEY=你的key
OPENAI_DEFAULT_MODEL=gpt-5.4-mini
OPENAI_MEAL_MODEL=gpt-5.4-mini
OPENAI_REPORT_MODEL=gpt-5.4-mini
```

`OPENAI_MEAL_MODEL` 和 `OPENAI_REPORT_MODEL` 可选；不设置时会使用
`OPENAI_DEFAULT_MODEL`。未配置 `OPENAI_API_KEY` 时，饮食 AI 和报表 AI 入口会隐藏，
普通记录、报表和备份不受影响。

AI 结果只用于个人记录辅助：

- 饮食 AI：照片和文字用于生成结构化识别结果，用户手动确认后才能应用到表单。
- 报表 AI：基于当前 7/30 天报表和最近记录摘要生成观察提示，不自动改数据。
- 日志追溯：`ai_analysis_runs` 只保存输入摘要 hash、输出 JSON、模型和错误，不保存图片 base64 或密钥。
- 安全口径：AI 输出不应作为诊断、处方、剂量或治疗建议。

如果 macOS Python 请求 OpenAI 时出现 `CERTIFICATE_VERIFY_FAILED`，先安装用户级证书包：

```bash
python3 -m pip install --user certifi
```

## 数据结构

完整建表语句在 `schema.sql`。如果之后要导出数据，可以直接使用 SQLite 工具读取 `data/ibs_fighter.sqlite3`。

## 项目结构

```text
IBS Fighter/
├── IBS_Fighter.py      # 本地应用启动入口
├── ibs_fighter/
│   ├── config.py       # 路径、端口、上传限制等配置
│   ├── db.py           # SQLite 初始化和迁移
│   ├── models.py       # 表字段配置
│   ├── crud.py         # 数据增删改查和今日汇总
│   ├── uploads.py      # 饮食照片保存
│   ├── reports.py      # 分类报表计算，目前包含排便、用药和体重
│   ├── ai_provider.py  # OpenAI Responses API JSON provider
│   ├── ai_analysis.py  # 饮食识别、报表复盘和 AI 日志
│   ├── openai_meal_analyzer.py # 饮食 AI 兼容入口
│   ├── server.py       # 本地 Web 服务和 API 路由
│   └── drive_backup.py # Google Drive 备份
├── schema.sql          # SQLite 建表和索引
├── start.sh            # macOS/Linux 启动脚本
├── static/
│   ├── index.html      # 页面结构
│   ├── styles.css      # 页面样式
│   └── js/
│       ├── app.js      # 浏览器端启动入口和事件绑定
│       ├── api.js      # API 请求封装
│       ├── constants.js # 前端表字段和标签配置
│       ├── forms.js    # 表单收集、回填、重置
│       ├── navigation.js # 标签页切换
│       ├── records.js  # 今日概览和记录列表渲染
│       ├── reports.js  # 报表请求和渲染
│       ├── state.js    # 前端共享状态
│       └── utils.js    # 日期、格式化、HTML 转义等工具
├── data/               # 本地数据库和个人数据，不提交到 GitHub
└── uploads/            # 饮食照片，不提交到 GitHub
```

## 报表口径

当前报表按分类独立计算，避免把不同类型的数据混在一起。

### 排便报表

- 总次数、平均每天次数、平均布里斯托等级
- 4-5 级占比，作为安全区比例
- 1-3 级归为低于安全区，6-7 级归为高于安全区
- Bristol 控制图会标记超出安全区的单次记录
- 安全率 p-chart 用于观察 Bristol 4-5 占比是否长期稳定
- 异常间隔 g-chart 用于观察两次非安全排便之间的安全间隔是否拉长
- 急迫感 3 分以上计入需要关注
- 一天 3 次及以上、低于/高于安全区、急迫感高的日期会进入关注列表
- 无记录日期会单独列出，后续需要区分“没有排便”和“忘记记录”

### 用药报表

- 总用药记录、使用天数、涉及药物种类、平均每天记录数
- 药物使用排行，包含次数、总数量、单位、使用天数
- 类型分布，例如处方药、益生菌、补剂
- 时间关系分布，例如饭前、饭后、睡前、空腹
- 一天 4 条及以上的高记录日会进入关注列表
- 无用药记录日期会单独列出，后续需要区分“未服用”和“忘记记录”

### 体重报表

- 最新体重、周期首末变化、平均体重、最高和最低体重
- 记录覆盖率和无记录日期，用来判断趋势可靠性
- 趋势图按每天最后一次体重记录绘制，避免同一天多次称重干扰周期趋势
- 较上次记录变化 1kg 以上的日期会进入关注列表
- 监控建议会提示把体重变化和排便、饮食、用药按 3-7 天窗口一起回看

## 隐私

`.gitignore` 会排除 `data/`、`uploads/`、`.DS_Store` 和 Python 缓存文件。发布到 GitHub 时只提交代码和结构，不提交本地健康数据库、Excel 原始记录或照片。
