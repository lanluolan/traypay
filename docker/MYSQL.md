# Docker MySQL 本地配置

后端在 Windows 运行，MySQL 在 Docker Desktop 的 Linux 容器运行。配置使用官方
[MySQL 镜像](https://hub.docker.com/_/mysql) `8.4.11`，字符集为 utf8mb4。

## 首次准备

在项目根目录执行：

```powershell
./scripts/setup-mysql.ps1
docker compose config --quiet
docker compose up -d --wait mysql
```

脚本仅创建项目根 `.env` 和 `backend/.env`，随机生成密码并保持应用密码一致。
文件已存在时脚本拒绝覆盖；不要为了重跑而删除原配置。
两份 `.env` 均被 `.gitignore` 忽略，不应提交。Docker 初始化变量只在空数据目录首次启动时生效，
修改 `.env` 不会自动更改已有数据库账户密码。

| 用途 | 地址 | 数据库 | 用户 | 数据保存方式 |
|---|---|---|---|---|
| 开发 | `127.0.0.1:3307` | `payment` | `checkout` | Docker 命名卷 `traypay_mysql_data`，重建容器保留 |
| 测试（可选） | `127.0.0.1:3308` | `payment_test` | `checkout_test` | 内存临时文件系统，容器停止后数据丢失 |

端口仅绑定本机。手机通过 Flask API 访问业务，不直接连接 MySQL。

## 后端建表

容器首次启动会创建数据库和应用账号；业务表与食堂管理员由现有 Flask 命令创建：

```powershell
cd backend
../.venv/Scripts/python -m flask --app manage init-db
```

前提是项目声明的后端及识别依赖已安装（见 [后端文档](../backend/README.md)）。
`init-db` 打印一次随机食堂管理员密码，重复执行不会重置已有管理员。
新生成的 `backend/.env` 已使用 `DB_HOST=127.0.0.1`、`DB_PORT=3307` 和专用账号。
如果进程环境中另有 `DATABASE_URL` 或 `DB_*`，它们可能覆盖文件配置，启动前检查。

## 检查与日常操作

```powershell
docker compose ps
docker compose logs --tail 50 mysql
docker compose exec mysql mysql -u checkout -p payment
docker compose stop mysql
docker compose start mysql
```

密码在项目根 `.env` 的 `MYSQL_PASSWORD` 中；交互式登录时输入，避免写进命令历史。
健康检查使用应用账户实际执行 `SELECT 1`，`up --wait` 等待数据库可用后返回。
`docker compose down` 保留开发数据卷；不要运行 `down -v`，它会删除开发数据。

## 可选：运行真实 MySQL 接口测试

独立测试服务使用 [Compose profile](https://docs.docker.com/compose/how-tos/profiles/)，正常启动开发库时不会启动它：

```powershell
docker compose --profile test up -d --wait mysql-test
$env:TEST_DATABASE_URL = 'mysql+pymysql://checkout_test:<根目录.env中的MYSQL_TEST_PASSWORD>@127.0.0.1:3308/payment_test'
cd backend
../.venv/Scripts/python -m unittest discover -s tests -t . -v
```

上面的连接串需替换密码占位符。测试会清空目标库，必须使用 `3308/payment_test`，不能指向开发库。
结束后回到项目根目录执行 `docker compose --profile test stop mysql-test`。

若未来把 Flask 也放进 Compose，数据库地址应改为服务名 `mysql:3306`；
当前的 `127.0.0.1:3307` 是供 Windows 上的后端使用。
