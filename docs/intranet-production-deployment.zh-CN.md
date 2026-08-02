# Auto Check 内网生产部署说明

本文适用于在内网生产服务器上部署 `auto-check` Linux 可执行文件。部署方式为：使用已创建好的 `autocheck` 专用用户运行服务，程序、配置、数据均放在 `/home/autocheck` 下，使用 systemd 管理后台服务。

## MySQL 应用库前置要求

当前版本的系统自身配置、用户、认证数据和执行历史统一保存到 MySQL 应用库 `auto_check`。生产部署前需完成以下工作，应用启动时只做连接和结构校验，不自动建库、建表、升级或迁移旧 SQLite 数据。

1. 在 MySQL 中手工创建 `auto_check` 数据库，并为应用账号授予必要读写权限。
2. 执行 `sql/app_storage/mysql/001_init_schema.sql` 创建 20 张应用存储表；该脚本不包含生产数据，也不包含 `CREATE DATABASE`、`DROP` 或 `TRUNCATE`。
3. 如需迁移旧 SQLite `auto-check.db`，停机备份后运行 `scripts/export_sqlite_to_mysql.py` 只读生成数据 SQL 和迁移报告，再由运维人员人工执行数据 SQL。
4. 执行 `sql/app_storage/mysql/002_report_navigation.sql` 新增 18 张报送导航表。
5. 执行 `sql/app_storage/mysql/003_report_navigation_seed.sql` 写入报送导航种子配置。
6. 执行 `sql/app_storage/mysql/004_user_interface_preferences.sql` 新增第 36 张用户界面偏好表。
7. 执行 `sql/app_storage/mysql/005_user_appearance_preferences.sql`，为用户偏好表增加折线图风格和两个可空的未来个人主题色字段及检查约束。
8. 执行 `sql/app_storage/mysql/006_system_interface_preferences.sql` 新增第 39 张系统界面偏好表；此时为模块系统升级前的 39 张表状态，随后继续按编号执行后续升级脚本。
9. 执行 `sql/app_storage/mysql/007_report_navigation_schedule_owner.sql`，为月度报送日程补充负责人字段。
10. 执行 `sql/app_storage/mysql/008_report_navigation_work_calendar.sql`，创建或更新法定节假日与调休工作日日历。
11. 执行 `sql/app_storage/mysql/009_report_navigation_manual_step_permissions.sql`，将当前允许人工确认的范围规范为“资管产品模板、逐笔报送”第七步。
12. 执行 `sql/app_storage/mysql/010_pbc_template_step_seven_display_only.sql`，将该第七步调整为仅展示，并将第六步作为最终完成节点。
13. 执行 `sql/app_storage/mysql/011_report_navigation_completion_time_sources.sql`，将归档类完成时间统一改为仅取 `create_date`，并配置人行大集中完成时间数据源。
14. 生产升级必须先备份 MySQL 应用库，再由运维人员人工执行 `sql/app_storage/mysql/012_module_system.sql`，新增 3 张模块平台表。
15. 执行 `sql/app_storage/mysql/013_report_navigation_provider_states.sql`，新增带注册 token 的报送导航统计提供方持久状态表，并为统计运行记录补充 `failed_providers`；完整应用结构共 43 张表，`app_schema_version` 仍为 `1`。模块业务表不加入全局 `EXPECTED_APP_SCHEMA`。
15. `/home/autocheck/data/config.json` 中只保留 `app_database` 启动连接信息和必要启动参数，动态配置、用户和历史记录不再写回 JSON。
16. `AUTO_CHECK_SECRET_KEY` 必须与旧环境保持一致，避免旧数据源加密密码无法解密。
17. 本地数据查询页面及入口已隐藏，不再提供 SQLite 查询、导出、备份或旧历史迁移入口，也不新增 MySQL 管理查询页面。
18. 上线验收需分别确认原 20 张迁移目标表的数据行数与迁移报告一致，以及当前完整 43 张应用存储表结构与配置升级（在备份下人工执行 `012_module_system.sql`、`013_report_navigation_provider_states.sql`）齐全；删除旧 SQLite `auto-check.db` 后应用仍应只依赖 MySQL 应用库运行。

升级脚本中，`004`、`006`、`008`、`012_module_system.sql` 和 `013_report_navigation_provider_states.sql` 使用 `CREATE TABLE IF NOT EXISTS`，`005` 与 `007` 通过 `information_schema` 判断结构是否存在；`004` 至 `013` 均按可重复执行方式编写。上线前仍须停机、备份并按顺序人工执行。`012`、`013` 不修改全局 schema version，生产环境不得由应用自动执行。

`user_interface_preferences` 按每个用户独立保存界面圆角和折线图风格，并预留两个可空的个人主题色，不设置外键，删除用户后的孤儿偏好由应用清理。`system_interface_preferences` 只保存系统级活力/沉稳纯色主题及最后修改人；主题色绝不写入 `app_settings`。从已执行 `001`、`002`、`003` 的版本升级时，应先停机和备份，在升级应用前依次执行随发布提供的 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`、`009_report_navigation_manual_step_permissions.sql`、`010_pbc_template_step_seven_display_only.sql`、`011_report_navigation_completion_time_sources.sql`；执行 `011` 后先备份并确认备份可用，再由运维人工执行 `012_module_system.sql`、`013_report_navigation_provider_states.sql`，再替换应用。`010` 将第七步改为仅展示并补齐第六步归档时间字段映射，`011` 将归档类完成时间统一改为仅取 `create_date`，并配置人行大集中从 `currency_report_24.currency_report_duration` 按报告期取最大 `create_date`。表已存在时仍需人工核对结构。本文仅描述运维步骤，不代表已在任何线上环境执行。

`app_database` 配置示例：

```json
{
  "app_database": {
    "backend": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "database": "auto_check",
    "username": "auto_check_app",
    "password": "<set-by-operations>",
    "charset": "utf8mb4"
  }
}
```

## 一、部署前提

### 1. 服务器环境

生产服务器建议满足：

```text
Linux x86_64
glibc >= 2.28
```

确认命令：

```bash
uname -m
getconf GNU_LIBC_VERSION
```

预期类似：

```text
x86_64
glibc 2.28
```

### 2. 用户已存在

本文假设专用用户已经创建：

```text
autocheck
```

确认：

```bash
id autocheck
getent passwd autocheck
```

家目录应为：

```text
/home/autocheck
```

### 3. 服务运行范围

本服务仅在内网环境运行，默认监听：

```text
0.0.0.0:8765
```

如只允许本机访问，可将监听地址改为：

```text
127.0.0.1
```

如只允许内网网卡访问，可将监听地址改为服务器内网 IP。

## 二、目录规划

所有应用相关文件放在 `/home/autocheck` 下：

```text
/home/autocheck/
├── app/
│   └── auto-check
├── data/
│   └── config.json
├── env/
│   └── auto-check.env
└── logs/
```

目录说明：

| 路径 | 用途 |
| --- | --- |
| `/home/autocheck/app` | 程序目录 |
| `/home/autocheck/app/auto-check` | Linux 可执行文件 |
| `/home/autocheck/data` | 配置、历史、上传文件等业务数据 |
| `/home/autocheck/env` | 环境变量文件 |
| `/home/autocheck/logs` | 预留日志目录，systemd 日志默认在 journalctl 中 |

创建目录：

```bash
sudo mkdir -p /home/autocheck/app
sudo mkdir -p /home/autocheck/data
sudo mkdir -p /home/autocheck/env
sudo mkdir -p /home/autocheck/logs
```

设置权限：

```bash
sudo chown -R autocheck:autocheck /home/autocheck
sudo chmod 750 /home/autocheck
sudo chmod 750 /home/autocheck/app
sudo chmod 750 /home/autocheck/data
sudo chmod 750 /home/autocheck/env
sudo chmod 750 /home/autocheck/logs
```

## 三、准备程序文件

### 1. 获取生产包

推荐使用东京服务器上 Docker 打包的 glibc 2.28 兼容包：

```bash
/opt/auto_check/dist-py38/auto-check
```

该包特性：

```text
Linux x86_64
Python 3.12.13
Debian 10 / glibc 2.28 构建
已包含 psycopg / psycopg_binary / pymysql
```

### 2. 上传到生产服务器

假设上传后的临时路径为：

```bash
/tmp/auto-check
```

复制到正式目录：

```bash
sudo cp /tmp/auto-check /home/autocheck/app/auto-check
sudo chown autocheck:autocheck /home/autocheck/app/auto-check
sudo chmod 755 /home/autocheck/app/auto-check
```

检查文件：

```bash
ls -lh /home/autocheck/app/auto-check
file /home/autocheck/app/auto-check
```

正常应看到：

```text
ELF 64-bit LSB executable, x86-64
```

## 四、验证程序可运行

使用 `autocheck` 用户执行：

```bash
sudo chmod 755 /home/autocheck/app/auto-check
/home/autocheck/app/auto-check --help
```

正常输出类似：

```text
usage: auto-check [-h] [--host HOST] [--port PORT] [--no-browser] [--config CONFIG]
```

如果此步骤失败，先不要配置 systemd，优先根据错误排查：

```bash
getconf GNU_LIBC_VERSION
file /home/autocheck/app/auto-check
ls -lh /home/autocheck/app/auto-check
```

## 五、创建环境变量文件

生成加密密钥：

```bash
SECRET_KEY=$(openssl rand -hex 32)
```

创建环境变量文件：

```bash
sudo tee /home/autocheck/env/auto-check.env >/dev/null <<EOF
AUTO_CHECK_HOST=0.0.0.0
AUTO_CHECK_PORT=8765
AUTO_CHECK_CONFIG=/home/autocheck/data/config.json
AUTO_CHECK_NO_BROWSER=1
AUTO_CHECK_SECRET_KEY=$SECRET_KEY
EOF
```

设置权限：

```bash
sudo chown autocheck:autocheck /home/autocheck/env/auto-check.env
sudo chmod 600 /home/autocheck/env/auto-check.env
```

查看配置：

```bash
sudo cat /home/autocheck/env/auto-check.env
```

配置说明：

| 配置项 | 说明 |
| --- | --- |
| `AUTO_CHECK_HOST=0.0.0.0` | 监听所有网卡，内网其他机器可访问 |
| `AUTO_CHECK_PORT=8765` | 服务端口 |
| `AUTO_CHECK_CONFIG=/home/autocheck/data/config.json` | 应用配置文件路径 |
| `AUTO_CHECK_NO_BROWSER=1` | 服务器启动时不自动打开浏览器 |
| `AUTO_CHECK_SECRET_KEY=...` | 数据库密码等敏感信息加密密钥 |

注意：`AUTO_CHECK_SECRET_KEY` 生成后不要随意修改。修改后，之前保存的加密密码可能无法解密。

### 内网监听建议

如果只允许内网访问，推荐两种方式：

#### 方式一：监听所有网卡，由防火墙/安全组限制来源

```text
AUTO_CHECK_HOST=0.0.0.0
```

这是最常用方式。

#### 方式二：只监听内网 IP

如果服务器内网 IP 为 `10.0.0.12`，可改为：

```text
AUTO_CHECK_HOST=10.0.0.12
```

修改后需要重启服务：

```bash
sudo systemctl restart auto-check
```

## 六、创建 systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
User=autocheck
Group=autocheck
WorkingDirectory=/home/autocheck/app
EnvironmentFile=/home/autocheck/env/auto-check.env
ExecStart=/home/autocheck/app/auto-check
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/home/autocheck

[Install]
WantedBy=multi-user.target
EOF
```

说明：

| 配置 | 说明 |
| --- | --- |
| `User=autocheck` | 服务以 autocheck 用户运行 |
| `WorkingDirectory=/home/autocheck/app` | 工作目录为程序目录 |
| `EnvironmentFile=/home/autocheck/env/auto-check.env` | 读取环境变量配置 |
| `ExecStart=/home/autocheck/app/auto-check` | 启动程序 |
| `Restart=on-failure` | 异常退出后自动重启 |
| `ProtectSystem=full` | 限制对系统目录的写权限 |
| `ReadWritePaths=/home/autocheck` | 允许写入应用家目录 |

## 七、启动服务

重新加载 systemd：

```bash
sudo systemctl daemon-reload
```

设置开机自启并立即启动：

```bash
sudo systemctl enable --now auto-check
```

查看状态：

```bash
sudo systemctl status auto-check --no-pager
```

正常状态应包含：

```text
Active: active (running)
```

确认进程用户：

```bash
ps -ef | grep auto-check | grep -v grep
```

应看到进程用户为：

```text
autocheck
```

## 八、访问验证

### 1. 本机验证

```bash
curl -I http://127.0.0.1:8765/
```

如果 `AUTO_CHECK_HOST` 配置为具体内网 IP，则使用对应 IP：

```bash
curl -I http://内网IP:8765/
```

正常应返回：

```text
HTTP/1.0 200 OK
```

### 2. 端口监听

```bash
ss -ltnp | grep 8765
```

正常可看到类似：

```text
LISTEN ... 0.0.0.0:8765
```

或：

```text
LISTEN ... 内网IP:8765
```

### 3. 浏览器访问

内网浏览器访问：

```text
http://服务器内网IP:8765
```

首次进入后：

1. 初始化管理员密码
2. 配置数据源
3. 测试 PostgreSQL / MySQL 连接

## 九、内网防火墙配置

如果服务器启用了 firewalld：

```bash
sudo systemctl status firewalld --no-pager
```

放行端口：

```bash
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

如果服务器还受云安全组、虚拟化平台安全策略或内网 ACL 控制，也需要放行：

```text
TCP 8765
```

建议仅允许内网网段访问，例如：

```text
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
```

具体以实际内网网段为准。

## 十、日志查看

查看实时日志：

```bash
sudo journalctl -u auto-check -f
```

查看最近 100 行日志：

```bash
sudo journalctl -u auto-check -n 100 --no-pager
```

查看最近 200 行日志：

```bash
sudo journalctl -u auto-check -n 200 --no-pager
```

如果服务启动失败，使用：

```bash
sudo systemctl status auto-check --no-pager
sudo journalctl -u auto-check -n 200 --no-pager
```

## 十一、常用服务命令

启动：

```bash
sudo systemctl start auto-check
```

停止：

```bash
sudo systemctl stop auto-check
```

重启：

```bash
sudo systemctl restart auto-check
```

查看状态：

```bash
sudo systemctl status auto-check --no-pager
```

设置开机自启：

```bash
sudo systemctl enable auto-check
```

取消开机自启：

```bash
sudo systemctl disable auto-check
```

## 十二、PostgreSQL 数据源连接检查

如果配置 PostgreSQL 数据源失败，先检查网络连通性。

### 1. 测试端口

PostgreSQL 默认端口：

```text
5432
```

使用 nc：

```bash
nc -vz PGSQL_HOST 5432
```

如果没有 nc，可用 bash 内置 TCP 测试：

```bash
timeout 3 bash -c '</dev/tcp/PGSQL_HOST/5432' && echo ok || echo fail
```

### 2. 检查数据库侧限制

需要确认数据库侧允许应用服务器访问：

```text
pg_hba.conf
数据库防火墙
数据库白名单
云安全组
内网 ACL
```

### 3. 驱动说明

当前生产包已包含：

```text
psycopg
psycopg_binary
pymysql
```

正常不需要在生产服务器额外安装 PostgreSQL 或 MySQL Python 驱动。

## 十三、更新版本

新包上传到：

```bash
/tmp/auto-check
```

执行更新：

```bash
sudo systemctl stop auto-check

sudo cp /home/autocheck/app/auto-check /home/autocheck/app/auto-check.bak.$(date +%Y%m%d-%H%M%S)

sudo cp /tmp/auto-check /home/autocheck/app/auto-check
sudo chown autocheck:autocheck /home/autocheck/app/auto-check
sudo chmod 755 /home/autocheck/app/auto-check

sudo -u autocheck /home/autocheck/app/auto-check --help

sudo systemctl start auto-check
sudo systemctl status auto-check --no-pager
```

如新版本异常，可回滚：

```bash
sudo systemctl stop auto-check
sudo cp /home/autocheck/app/auto-check.bak.时间戳 /home/autocheck/app/auto-check
sudo chown autocheck:autocheck /home/autocheck/app/auto-check
sudo chmod 755 /home/autocheck/app/auto-check
sudo systemctl start auto-check
```

## 十四、数据备份

### 1. 备份全部应用目录

```bash
sudo tar -czf /tmp/autocheck-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /home autocheck
```

### 2. 只备份业务数据

```bash
sudo tar -czf /tmp/autocheck-data-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /home/autocheck data
```

### 3. 恢复业务数据

```bash
sudo systemctl stop auto-check
sudo mv /home/autocheck/data /home/autocheck/data.bak.$(date +%Y%m%d-%H%M%S)
sudo tar -xzf /tmp/autocheck-data-backup-YYYYMMDD-HHMMSS.tar.gz -C /home/autocheck
sudo chown -R autocheck:autocheck /home/autocheck/data
sudo systemctl start auto-check
```

## 十五、完整快速部署命令

以下命令适用于：

- `autocheck` 用户已经存在
- 程序包已经上传到 `/tmp/auto-check`
- 服务端口使用 `8765`
- 服务仅在内网访问

```bash
sudo mkdir -p /home/autocheck/app /home/autocheck/data /home/autocheck/env /home/autocheck/logs

sudo cp /tmp/auto-check /home/autocheck/app/auto-check

sudo chown -R autocheck:autocheck /home/autocheck
sudo chmod 750 /home/autocheck
sudo chmod 750 /home/autocheck/app
sudo chmod 750 /home/autocheck/data
sudo chmod 750 /home/autocheck/env
sudo chmod 750 /home/autocheck/logs
sudo chmod 755 /home/autocheck/app/auto-check

sudo -u autocheck /home/autocheck/app/auto-check --help

SECRET_KEY=$(openssl rand -hex 32)

sudo tee /home/autocheck/env/auto-check.env >/dev/null <<EOF
AUTO_CHECK_HOST=0.0.0.0
AUTO_CHECK_PORT=8765
AUTO_CHECK_CONFIG=/home/autocheck/data/config.json
AUTO_CHECK_NO_BROWSER=1
AUTO_CHECK_SECRET_KEY=$SECRET_KEY
EOF

sudo chown autocheck:autocheck /home/autocheck/env/auto-check.env
sudo chmod 600 /home/autocheck/env/auto-check.env

sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
User=autocheck
Group=autocheck
WorkingDirectory=/home/autocheck/app
EnvironmentFile=/home/autocheck/env/auto-check.env
ExecStart=/home/autocheck/app/auto-check
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/home/autocheck

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now auto-check
sudo systemctl status auto-check --no-pager
```

如果 firewalld 已启用，需要放行内网访问端口：

```bash
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

访问：

```text
http://服务器内网IP:8765
```
