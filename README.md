# IBS Fighter

一个本地运行的 IBS 日常追踪工具，用 SQLite 保存数据，当前覆盖：

- 排便：时间、布里斯托 1-7 级、地点、急迫感、颜色、备注
- 饮食：时间、餐别、地点历史下拉、历史快捷填充、照片、文字描述、饭后反应、备注
- 药物登记：药物名称、成分、类型、固定单位
- 用药：时间、勾选一个或多个已登记药物、分别填写数量，单位从药物登记自动带出、服用时间关系、备注
- 运动：时间、常用活动快捷填充、活动文本、时长、强度、备注
- 今日检查：排便、三餐、用药和运动是否已记录，帮助发现漏记
- 报表：按分类查看排便和用药，支持 7 天和 30 天周期
- OpenAI 测试：饮食照片/文字识别，结果用于辅助填写文字描述

## 运行

仅在这台电脑上使用：

```bash
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

这个阶段还没有登录系统。使用 `./start.sh` 会让同一局域网里的设备可以访问，请只在可信 Wi-Fi 下使用。

当前定位是本地个人版。一周试用稳定后发布到 GitHub 的仍然只是代码和说明，不包含你的本地数据库、照片或 Excel 原始记录。

数据库文件会自动创建在：

```text
data/ibs_fighter.sqlite3
```

饮食照片会保存在：

```text
uploads/
```

## OpenAI 饮食识别测试

OpenAI API key 保存在本机 `.env`，不要提交到 GitHub：

```text
OPENAI_API_KEY=你的key
```

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
│   ├── reports.py      # 分类报表计算，目前包含排便和用药
│   ├── openai_meal_analyzer.py # OpenAI 饮食识别测试
│   ├── server.py       # 本地 Web 服务和 API 路由
│   └── drive_backup.py # 之后接 Google Drive 备份
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
- 3-5 级占比，作为相对正常比例
- 1-2 级归为偏硬，6-7 级归为偏稀
- 急迫感 3 分以上计入需要关注
- 一天 3 次及以上、偏硬/偏稀、急迫感高的日期会进入关注列表
- 无记录日期会单独列出，后续需要区分“没有排便”和“忘记记录”

### 用药报表

- 总用药记录、使用天数、涉及药物种类、平均每天记录数
- 每日用药趋势
- 药物使用排行，包含次数、总数量、单位、使用天数
- 类型分布，例如处方药、益生菌、补剂
- 时间关系分布，例如饭前、饭后、睡前、空腹
- 一天 4 条及以上的高记录日会进入关注列表
- 无用药记录日期会单独列出，后续需要区分“未服用”和“忘记记录”

## 隐私

`.gitignore` 会排除 `data/`、`uploads/`、`.DS_Store` 和 Python 缓存文件。发布到 GitHub 时只提交代码和结构，不提交本地健康数据库、Excel 原始记录或照片。
