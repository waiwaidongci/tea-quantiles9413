# 青禾茶样分布检验册

茶样含水率与浸出率批次→分布研究→复测抽样建议；不可将bootstrap区间称预测区间。原生 HTML/CSS/JavaScript 多模块工作席，所有计算由 Python 完成。

## 模拟业务
青禾研究协作组，12名分析师与业务人员，日常使用 `tea-quantiles-202611-1.csv` 手工抄表。当前三个痛点：观测与口径不可追溯、重算易出错、结果与复核割裂。上游提供独立合成业务观测；本应用接管数据登记、方法执行和输入冻结；下游负责人形成复测/预算方案，观察员获取复核后的CSV。

核心业务实体：TeaLot / TastingReading / DistributionRun / ReleaseNote。源码 model/schema/service/controller/route 与前端 api/store/pages 完成链路，不依赖浏览器本地假数据。

## 功能与方法
- 茶样批次、浸出观测录入/编辑/删除；重名记录与非法数值明确拒绝。
- 分位数、ECDF与按批bootstrap中位数区间。中位数置信区间描述估计不确定性，不是下一份茶样的预测区间。
- 每次运行冻结参数、观测和SHA256。Redis任务由独立worker计算，写DB与共享产物卷；输入修改不会改写历史结果。
- 负责人复核不可覆盖；审计记录登录、数据改动、排队、复核与导出；240请求/分钟限流、全局可恢复错误。
- 受保护分布发布：批次固定指标、分箱与总隐私预算；每次按“增删一份茶样”灵敏度1加拉普拉斯噪声，ECDF与分位数只由同一份非负箱计数推导。冻结输入+分箱+本次预算构成指纹，改名或并发重试复用发布，不重抽噪声、不重复扣费；余额不足返回409。扣费、扰动结果与留档齐全后才开放查看/下载；留档失败保留原结果，重试只重写留档。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18240 ，API http://localhost:19240/docs 。数据库映射 17740。无需Node构建。可以从中文和带空格目录启动。清理 `docker compose down -v --remove-orphans` 会删除本题演示数据卷。

|角色|账号|密码|权限与典型动作|
|---|---|---|---|
|admin 负责人|admin@demo.local|Research2026!|全部读写、设定受保护口径、批准复核、下载|
|analyst 分析师|analyst@demo.local|Research2026!|数据修改、创建任务、申请受保护发布、读取结果及下载；不能复核|
|viewer 观察员|viewer@demo.local|Research2026!|只读；受保护批次只见受保护分布与扣费收据，不读原值、精确计数与历史精确研究|

## 一天的工作剧本
1. 09:00 admin登录，查“青禾·秋制一号”。
2. 09:10 analyst核对 `tea-quantiles-202611-1.csv` 的seed记录。
3. 09:15 来源录入页检查 `含水率 (%)` 等业务字段，必要时编辑。
4. 09:20 分析执行页保留默认参数 `{"field": "moisture", "resamples": 2000}`，命名本轮研究。
5. 09:21 冻结输入并排队，worker实算，结果页自动刷新。
6. 09:25 阅读核心数值、方法边界、明细与SHA256；发现失败先修数据重跑。
7. 09:35 admin打开业务复核，写明限制与下一步动作，归档后不可覆盖。
8. 09:40 viewer读取复核意见并下载CSV，在操作留痕页核对下载事件。
9. 09:50 admin在“受保护发布”冻结分箱与总预算，analyst提交受保护发布；待生成到可用后viewer查看/下载，观察员在来源页看不到该批次原值与条数。

## 技术与目录
|部分|实现|
|---|---|
|前端|原生ES modules、HTML/CSS、Nginx1.27，无前端框架|
|API|Python3.11、FastAPI0.115、SQLAlchemy2、JWT、PBKDF2密码|
|计算|NumPy2.2、SciPy1.15，固定seed42|
|数据库|PostgreSQL16|
|任务|Redis7持久队列，Python独立worker，心跳healthcheck|

`frontend/src/`分api、stores、types、components/common、hooks、pages、router、utils、constants；`backend/src/`分config、models、schemas、services、controllers、routes、middlewares、utils、constants；`backend/scripts/seed_demo.py`自然键插入、重复不覆盖修改；`backend/migrations/README.md`说明schema版本。

环境变量 `.env.example`：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO；可选 `ARTIFACT_DIR` 指定留档目录（默认 `/app/artifacts`）。开发时在本地venv安装backend/requirements.txt，设置DATABASE_URL、REDIS_URL、JWT_SECRET再运行uvicorn；前端开发经Nginx代理 `/api/` 到不带前缀的API。

受保护发布状态为pending/generating/available/failed；预算以百万分之一整数记账，扣费为条件UPDATE，与发布行插入同一事务。观察员的全部入口（overview、studies、observations、runs、audits、export）对受保护批次隐藏原值、精确行数与旧精确研究。

共享枚举：角色admin/analyst/viewer和队列queued/running/completed/failed；后端`src/constants/enums.py`、认证与worker使用相同值；前端`src/types/enums.js`、状态与角色界面使用相同值。Google Fonts：Noto Serif SC + IBM Plex Mono；断网使用serif/monospace回退。

## 算法输入、失败态与复现
输入为选定批次全部观测和参数，输出核心数值、明细、解释；参数经后端严格白名单和范围验证。中位数置信区间描述估计不确定性，不是下一份茶样的预测区间。。空批次拒绝；不完整字段/非有限数/非法计数拒绝；常量相关列与不足样本使任务failed并保留错误。固定seed42、输入checksum相同可复现。独立oracle：按线性插值手算分位数；固定seed重采样复现；常量与空组边界。

已知边界：小型本地研究应用，使用合成数据，不含企业SSO与外发邮件；结果由人工复核，不自动执行业务决策；单worker恢复queued/running任务，数据库与Redis间未采用分布式事务。受保护分布的分位数在固定分箱内插值，带分组误差；负噪声计数截为0会引入小偏差；预算账本为单库事务，跨库并发依赖数据库的条件UPDATE。以 `backend/TESTING.md` 记录实际验证结果。

MIT License。
