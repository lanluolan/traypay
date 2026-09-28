# backend — Flask 结算服务

Flask + Flask-SQLAlchemy + MySQL，路由分四组：`/user/*`（顾客）、
`/admin/*`（食堂结算与统计）、`/cuisine/*`（菜品库管理）、`/healthz`（探活）。
菜品识别用本仓库的 [../recognition](../recognition/) 模块，无外部 API 依赖。

## 应用装配

`payment` 包导出的是**工厂函数** `create_app(env=None)`，不是模块级的 `app`：

```python
from payment import create_app
app = create_app()          # env 取 $APP_ENV，未设置时为 'pro'
```

- `APP_ENV` 只认 `dev` / `pro`。**代码里的默认值是 `pro`** —— 必须显式选择才会
  开 DEBUG（也就是 Werkzeug 交互式调试器，那是远程代码执行入口）。
- 无论用什么方式启动，**工作目录必须是 `backend/`**：视图把上传图写到
  `static/cuisine/...` 这类相对 CWD 的路径。

## 本地启动

MySQL 可以直接使用项目根目录的 Compose 配置，步骤见 [Docker MySQL 配置](../docker/MYSQL.md)。
准备脚本会生成匹配的 `backend/.env`，此时无需再复制模板覆盖它。

```powershell
cd backend
pip install -e "../recognition[yolo]"  # dish_recognition 及其依赖（含 torch）
pip install -r requirements.txt
copy .env.example .env                 # 填数据库账号、生成 SECRET_KEY
flask --app manage init-db             # 建表 + 创建食堂端账号（见下）
$env:APP_ENV="dev"; python manage.py   # 开发服务器，仅限本机
```

> ⚠️ 用真机或模拟器测 App 时会想把 `FLASK_RUN_HOST` 改成 `0.0.0.0` —— 那一刻
> Werkzeug 调试器就暴露给整个局域网了。**改 host 必须同时把 `APP_ENV` 改回 `pro`。**

## 建库：`init-db`

模型定义在 [payment/models.py](payment/models.py)，但**没有任何东西会自动建表** ——
空库必须先跑一次：

```powershell
flask --app manage init-db
# 可选参数：--admin-name / --admin-password / --store-name / --address
```

`--admin-password` 不指定就随机生成并**只打印一次**。`/admin/*` 没有注册接口，
食堂端账号只能由这个命令（或手工 INSERT）创建 —— 这是刻意的：能自助注册的
管理员账号等于没有管理员。

命令可重复执行：`create_all()` 只补建缺失的表，**已存在的管理员不会被覆盖，
密码也不会被重置**。

## 鉴权

登录签发 token（[payment/auth.py](payment/auth.py)），之后每个请求带
`Authorization: Bearer <token>`。token 由 `SECRET_KEY` 签名，**生产环境不设它会
拒绝启动** —— 内置默认密钥等于公开密钥，任何人都能伪造任意账号的 token。

| 接口 | 要求 |
|---|---|
| `/healthz`、`/user/login`、`/user/register`、`/admin/login` | 公开 |
| `/user/recharge`、`/user/query/record/*` | 顾客**本人** 或 **任一管理员** |
| `/user/delete` | 管理员 |
| `/admin/*`、`/cuisine/*` | 管理员；带 `a_id` 的**必须是自己那家店** |

「顾客本人**或**管理员」不是偷懒：食堂端 App 要在柜台给顾客充值
（`/user/recharge`）、查顾客消费明细（`/user/query/record/detail`）。写成「仅本人」
会直接锁死食堂端。

**光有 token 不算授权。** 知道调用者是谁，不等于他能动他指名的那条记录 —— 所以每个
接收 `u_id` / `a_id` 的接口都还要过一遍 `acting_for_user` / `acting_for_admin`。
否则任何登录账号仍能操作别人的钱，那才是这套东西真正要堵的洞。

- **401** = 没有可用 token（缺失、签名不对、已过期）→ 客户端应跳登录
- **403** = token 有效但无权（角色不对，或 id 不是自己）→ 提示权限不足

token 是无状态的，**没有服务端吊销**。要提前失效只能缩短 `AUTH_TOKEN_MAX_AGE`
（默认 7 天）或轮换 `SECRET_KEY`（会让所有已签发 token 立即作废）。

## 健康检查

`GET /healthz`（[payment/views/health.py](payment/views/health.py)）：

```json
{"status":"ok","database":"ok",
 "recognizer":{"loaded":true,"detector":"YoloDishDetector","dishes":12,"vectors":96},
 "warnings":[]}
```

- 数据库不可达 → **503**，让负载均衡摘掉这个实例
- **检测器降级**进入探活 `warnings`，不影响人工录单等功能；`/admin/detect` 会明确拒绝整图识别并返回 503。应监控并恢复检测器。
- 探活**不会**触发模型加载（见 `legacy_api.status()`），冷容器上也是廉价请求

## Docker

> **后端容器不是跑起来的必要条件。** 本机开发直接 `python manage.py` 即可，只需要
> 一个能连的 MySQL。容器用于：验证生产姿态（Windows 装不了 gunicorn，见
> [requirements.txt](requirements.txt) 的平台标记）、用真机测局域网、以及部署。

### 构建

在**仓库根目录**执行，构建上下文需包含 `recognition/`：

```powershell
docker build -f backend/Dockerfile -t smart-checkout-backend .
```

### 起容器

```powershell
docker run -d --name checkout-backend --network checkout-net `
  -e DB_USER=checkout -e DB_PASSWORD=<应用密码> `
  -e DB_HOST=checkout-mysql -e DB_PORT=3306 -e DB_NAME=payment `
  -e APP_ENV=pro -e SECRET_KEY=<和 .env 里同一个值> `
  -p 0.0.0.0:5000:5000 `
  -v checkout_store:/srv/backend/dish_feature_store `
  -v checkout_static:/srv/backend/static `
  smart-checkout-backend
```

四个参数别照 `.env` 抄：

| 参数 | 为什么不能照抄 `.env` |
|---|---|
| `DB_HOST=checkout-mysql` | `.env` 里是 `127.0.0.1`，在容器里指的是**容器自己**。用服务名走 docker 网络（或 `host.docker.internal` 连宿主机） |
| `DB_PORT=3306` | `.env` 里可能是 3307，那是**宿主机**的映射端口。容器之间走内网，用容器自己的 3306 |
| `SECRET_KEY` | 必须显式传。不传的话 `APP_ENV=pro` 会**拒绝启动**，而且换了值会让所有已签发 token 失效 |
| `APP_ENV=pro` | 别用 `dev`：那会开 Werkzeug 调试器，而 `-p 0.0.0.0` 已经把端口暴露给整个局域网 |

因为这些差异，**`--env-file backend/.env` 不能直接用**。

**两个挂卷不是可选的**：`dish_feature_store` 丢了等于所有菜要重新录入，
`static` 丢了等于注册图没了。

### 镜像里的两处成本前置

- **CPU 版 torch**，单独从 PyTorch 自己的索引装。Linux 上 PyPI 的默认 wheel 是
  CUDA 版，会拖进约 2 GB CPU 部署根本不会执行的 `nvidia-*` 运行库
- **构建时预热 ResNet50 权重**。否则 torchvision 会在首次调用时下载约 100 MB 到
  `~/.cache/torch` —— 那不是挂载卷，容器每次重启都要重下，首个 `/admin/detect`
  连 120 秒超时都撑不住

### gunicorn 的三个参数

| 参数 | 为什么 |
|---|---|
| `--workers 1` | **必须是 1，这不是性能旋钮。** 特征库是进程内单例，构造时从磁盘读一次。开 2 个 worker 时，`/cuisine/add` 上新的菜只进了其中一个的内存，另一个继续用旧库、认不出这道菜，直到重启；而请求落到哪个 worker 是随机的，症状就是「上新后时灵时不灵」。要横向扩展得先做共享特征库，不是加 worker |
| `--threads 4` | 给数据库型接口（登录、查询、结算）留并发，免得一次约 1 秒的 `/admin/detect` 把它们全堵住。识别本身由 `legacy_api` 的锁串行化 |
| `--timeout 120` | 首次 `/admin/detect` 要加载甚至下载 ResNet50，远超默认 30 秒，否则 worker 会被杀掉 |

## 几处刻意为之的设计

| 决定 | 原因 |
|---|---|
| `/admin/detect` **不去重**，同一道菜两份返回两条、计价两次 | 去重会丢失份数信息，直接少收钱 |
| `/cuisine/add` 的 `img` 支持多文件，响应带可选 `conflicts` | 多角度注册显著提升识别稳健性；相似冲突交给经办人处理 |
| `/admin/purchase` 扣款与写消费记录合并为**单个事务** | 分开提交时中途失败会扣钱无订单 |
| `/admin/purchase` 要求签名草稿、逐区域 review 和整盘确认，并重新计价 | 未处理区域不能扣款；详见 [识别流程](../recognition/WORKFLOW.md)，食堂端必须同步升级 |
| 密码用 werkzeug 哈希（`generate_password_hash`），列宽 VARCHAR(255) | 默认 scrypt 哈希是 **162 字符**，VARCHAR(40) 存不下，MySQL 严格模式下注册直接失败 |
| `Cuisine.c_price` DECIMAL(6,2)、`User.u_money` DECIMAL(8,2) | DECIMAL(2,2) 只能存 0.00–0.99，无法表示真实价格 |
| 模型 `default=datetime.now`（函数，不是 `datetime.now()`） | 写成调用结果的话，所有行的默认时间都是**服务启动时刻** |
| 所有错误响应都是 JSON（[errors.py](payment/errors.py)） | 两端客户端对每个响应都 `json.decode`，HTML 错误页会让 App 卡在解析步骤 |
| `/user/query/record/*` 的 GROUP BY 带上 `a_store_name`/`a_address` | MySQL 8 默认开 ONLY_FULL_GROUP_BY，不带会报 1055 直接 500 |
| `/cuisine/query/all` 按**行位置**分页而非主键值 | 删除会让 `c_id` 出现空洞，按值分页会漏掉整段菜品 |

## 测试

```powershell
cd backend
python -m unittest discover -s tests -t .    # -t . 让 payment 可导入
```

| 文件 | 需要 MySQL？ | 覆盖 |
|---|---|---|
| [tests/test_auth.py](tests/test_auth.py) | 否，已进 CI | 401/403 的边界、token 过期与换签名、`acting_for_*` 的越权判断 |
| [tests/test_recognition_workflow.py](tests/test_recognition_workflow.py) | 否，隔离 SQLite + 模拟识别 | 区域确认、人工录单、样本管理及失败回滚；不替代 MySQL 并发验证 |
| [tests/test_api_integration.py](tests/test_api_integration.py) | **是**（不设 `TEST_DATABASE_URL` 则整体跳过） | 注册登录、越权充值、同菜两份计价两次、扣款事务回滚、下架保护、JSON 错误页 |

集成测试**自带夹具**，不依赖任何预置数据，但会清空所指库的表 ——
`TEST_DATABASE_URL` 一定要指向一次性的库，不是开发库。

## 已知遗留问题

见仓库根的 [../ISSUES.md](../ISSUES.md)。识别流程修改不代表充值、订单幂等和历史账目等问题已全部解决。
