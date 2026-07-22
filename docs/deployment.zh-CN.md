# Auto Check 部署说明

当前版本使用 MySQL 应用库保存系统自身配置、用户、认证数据和执行历史。部署时仍按单实例处理：只在一台机器上启动一个服务进程，Windows 或 Linux 客户端通过服务端 IP 和固定端口访问。

## MySQL 应用库前置准备

上线前必须由运维人员手工准备 MySQL 应用库 `auto_check`，应用启动时只连接和校验表结构，不自动建库、建表、升级或迁移 SQLite 数据。

1. 手工创建空库 `auto_check`，并为应用账号授予必要读写权限。
2. 执行 `sql/app_storage/mysql/001_init_schema.sql` 创建 20 张应用存储表；该脚本不包含生产数据，也不包含 `CREATE DATABASE`、`DROP` 或 `TRUNCATE`。
3. 如需迁移旧 SQLite `auto-check.db`，停机备份后运行 `scripts/export_sqlite_to_mysql.py` 只读生成数据 SQL 和迁移报告，再由运维人员人工执行数据 SQL。
4. 执行 `sql/app_storage/mysql/002_report_navigation.sql` 新增 17 张报送导航表。
5. 执行 `sql/app_storage/mysql/003_report_navigation_seed.sql` 写入报送导航种子配置。
6. 执行 `sql/app_storage/mysql/004_user_interface_preferences.sql` 新增第 36 张用户界面偏好表。
7. 执行 `sql/app_storage/mysql/005_user_appearance_preferences.sql`，为用户偏好表增加折线图风格和两个可空的未来个人主题色字段及检查约束。
8. 执行 `sql/app_storage/mysql/006_system_interface_preferences.sql` 新增第 39 张系统界面偏好表；完整应用结构共 39 张表，`app_schema_version` 仍为 `1`。
9. 执行 `sql/app_storage/mysql/007_report_navigation_schedule_owner.sql`，为月度报送日程补充负责人字段。
10. 执行 `sql/app_storage/mysql/008_report_navigation_work_calendar.sql`，创建或更新法定节假日与调休工作日日历。
11. 在 `config.json` 中配置 `app_database`，`config.json` 仅保留 `app_database` 启动连接信息，不再保存动态配置、用户或历史数据。
12. 保持 `AUTO_CHECK_SECRET_KEY` 与旧环境一致，避免旧数据源加密密码无法解密。
13. 本地数据查询页面及入口已隐藏，不再提供 SQLite 查询、导出、备份或旧历史迁移入口，也不新增 MySQL 管理查询页面。
14. 上线验收需分别确认原 20 张迁移目标表的数据行数与迁移报告一致，以及当前完整 39 张应用存储表结构（依次执行 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`）齐全；删除旧 SQLite `auto-check.db` 后应用仍应只依赖 MySQL 应用库运行。

`user_interface_preferences` 按每个用户独立保存界面圆角和折线图风格，并预留两个可空的个人主题色，不设置外键，删除用户后的孤儿偏好由应用清理。`system_interface_preferences` 只保存系统级活力/沉稳纯色主题及最后修改人；主题色绝不写入 `app_settings`。从已执行 `001`、`002`、`003` 的版本升级时，应先停机和备份，在升级应用前依次执行随发布提供的 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`，再替换应用。`004`、`006` 和 `008` 采用 `CREATE TABLE IF NOT EXISTS`，`005` 与 `007` 通过 `information_schema` 判断字段或约束后再升级；五个脚本均可重复执行，不会重复建表、重复加列或删除现有数据，表已存在时仍需人工核对结构。本文仅描述运维步骤，不代表已在任何线上环境执行。

`app_database` 示例：

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

本系统面向桌面端浏览器使用，建议在常规电脑屏幕或浏览器窗口宽度不低于 `900px` 的环境下操作；移动端、390px 等极窄屏不纳入本版本部署验收范围。

## 端口策略

应用默认端口固定为 `8765`，但端口号可以配置。部署时推荐仍使用一个明确固定值，不使用随机端口。

支持三种配置方式，优先级从高到低：

1. 命令行参数：`--port 8765`
2. 环境变量：`AUTO_CHECK_PORT=8765`
3. 程序默认值：`8765`

常用环境变量：

- `AUTO_CHECK_HOST`：监听地址。局域网访问使用 `0.0.0.0`。
- `AUTO_CHECK_PORT`：监听端口，默认 `8765`。
- `AUTO_CHECK_CONFIG`：配置文件路径，例如 `/var/lib/auto-check/config.json`。
- `AUTO_CHECK_NO_BROWSER`：设置为 `1` 时不自动打开浏览器。
- `AUTO_CHECK_SECRET_KEY`：建议生产部署固定设置，用于加密配置中的数据库密码。

端口示例：

```sh
AUTO_CHECK_HOST=0.0.0.0 AUTO_CHECK_PORT=8765 scripts/run-deployed-linux.sh
```

如需改为 `18080`：

```sh
AUTO_CHECK_HOST=0.0.0.0 AUTO_CHECK_PORT=18080 scripts/run-deployed-linux.sh
```

访问地址相应变为：

```text
http://<server-ip>:18080
```

## Windows 部署

先打包 Windows 可执行文件：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

再用固定端口启动部署服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-deployed-windows.ps1
```

默认监听 `0.0.0.0:8765`。同一内网的其他机器通过以下地址访问：

```text
http://<server-ip>:8765
```

如需显式指定监听地址、端口和配置文件：

```powershell
$env:AUTO_CHECK_HOST = "0.0.0.0"
$env:AUTO_CHECK_PORT = "8765"
$env:AUTO_CHECK_CONFIG = "D:\auto-check-data\config.json"
powershell -ExecutionPolicy Bypass -File scripts\run-deployed-windows.ps1
```

## Linux 部署目标

推荐路径：

```text
/opt/auto_check              应用代码
/var/lib/auto-check          应用配置、用户、历史等本地数据
/etc/auto-check/auto-check.env  systemd 环境变量文件
```

建议使用普通服务用户运行，不建议直接用 `root` 长期运行应用。

## Linux 环境准备

Ubuntu/Debian：

```sh
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git unzip
```

如果发行版源里没有 `python3.12`，可先用系统自带 Python 3.12 环境或自行安装 Python 3.12，再确认：

```sh
python3.12 --version
```

Rocky Linux/CentOS/AlmaLinux：

```sh
sudo dnf install -y python3.12 python3.12-devel git
```

确认可用：

```sh
python3.12 --version
```

## 上传项目

方式一：服务器能访问代码仓库时，在服务器克隆或拉取代码：

```sh
sudo mkdir -p /opt/auto_check
sudo chown "$USER":"$USER" /opt/auto_check
git clone <repo-url> /opt/auto_check
```

方式二：从本机打包上传：

```sh
tar -czf auto_check.tar.gz --exclude .git --exclude build --exclude .pytest_cache --exclude __pycache__ .
scp auto_check.tar.gz <user>@<server-ip>:/tmp/
ssh <user>@<server-ip> 'sudo mkdir -p /opt/auto_check && sudo tar -xzf /tmp/auto_check.tar.gz -C /opt/auto_check'
```

## 安装依赖

进入应用目录：

```sh
cd /opt/auto_check
```

创建虚拟环境：

```sh
python3.12 -m venv .venv
. .venv/bin/activate
```

安装项目依赖：

```sh
python -m pip install --upgrade pip
python -m pip install -e .
```

如需在服务器上运行测试：

```sh
python -m pip install -e .[dev]
python -m pytest -q
```

## 创建数据目录

```sh
sudo mkdir -p /var/lib/auto-check
sudo chown "$USER":"$USER" /var/lib/auto-check
```

如果已有本地配置文件，可上传为：

```text
/var/lib/auto-check/config.json
```

没有配置文件时，首次访问页面后按界面初始化管理员密码和数据源配置。

## 手动启动验证

先手动启动一次：

```sh
cd /opt/auto_check
. .venv/bin/activate
AUTO_CHECK_HOST=0.0.0.0 \
AUTO_CHECK_PORT=8765 \
AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json \
AUTO_CHECK_NO_BROWSER=1 \
scripts/run-deployed-linux.sh
```

本机检查：

```sh
curl -I http://127.0.0.1:8765/
```

客户端访问：

```text
http://<server-ip>:8765
```

如果端口改成 `18080`，启动和检查命令里的端口也同步改为 `18080`。

## systemd 部署

创建环境变量文件：

```sh
sudo mkdir -p /etc/auto-check
sudo tee /etc/auto-check/auto-check.env >/dev/null <<'EOF'
AUTO_CHECK_HOST=0.0.0.0
AUTO_CHECK_PORT=8765
AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json
AUTO_CHECK_NO_BROWSER=1
AUTO_CHECK_SECRET_KEY=change-this-to-a-long-random-string
EOF
```

创建服务文件：

```sh
sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/auto_check
EnvironmentFile=/etc/auto-check/auto-check.env
ExecStart=/opt/auto_check/.venv/bin/python -m auto_check
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

加载并启动：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now auto-check
sudo systemctl status auto-check --no-pager
```

查看日志：

```sh
journalctl -u auto-check -f
```

重启服务：

```sh
sudo systemctl restart auto-check
```

停止服务：

```sh
sudo systemctl stop auto-check
```

## 开放防火墙端口

Ubuntu/Debian 常见 `ufw`：

```sh
sudo ufw allow 8765/tcp
sudo ufw status
```

Rocky/CentOS/AlmaLinux 常见 `firewalld`：

```sh
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

云服务器还需要在云厂商安全组中放行同一个 TCP 端口。

## 更新部署

更新前先备份本地数据：

```sh
sudo systemctl stop auto-check
sudo tar -czf /var/lib/auto-check-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /var/lib auto-check
```

如果使用 git 部署：

```sh
cd /opt/auto_check
git pull
. .venv/bin/activate
python -m pip install -e .
python -m pytest -q
sudo systemctl start auto-check
```

如果使用压缩包部署，先上传新包，再解压覆盖 `/opt/auto_check`，然后重新安装依赖并启动服务。

## 回滚

如果更新后服务异常：

```sh
sudo systemctl stop auto-check
cd /opt/auto_check
git log --oneline -5
git checkout <last-good-commit>
. .venv/bin/activate
python -m pip install -e .
sudo systemctl start auto-check
```

如果需要恢复本地数据：

```sh
sudo systemctl stop auto-check
sudo rm -rf /var/lib/auto-check
sudo tar -xzf /var/lib/auto-check-backup-YYYYMMDD-HHMMSS.tar.gz -C /var/lib
sudo systemctl start auto-check
```

## 常见问题

端口被占用：

```sh
sudo ss -ltnp | grep ':8765'
```

服务没有监听外网地址：

```sh
sudo systemctl cat auto-check
sudo systemctl restart auto-check
sudo ss -ltnp | grep ':8765'
```

确认 `AUTO_CHECK_HOST=0.0.0.0` 已在 `/etc/auto-check/auto-check.env` 中配置。

页面打不开：

```sh
curl -I http://127.0.0.1:8765/
journalctl -u auto-check -n 100 --no-pager
```

数据库密码解不开：

```sh
sudo systemctl stop auto-check
sudo grep AUTO_CHECK_SECRET_KEY /etc/auto-check/auto-check.env
```

`AUTO_CHECK_SECRET_KEY` 一旦用于保存加密密码，迁移或重启时应保持一致。

## 安全建议

- 只在可信内网或 VPN 中开放服务。
- 不要直接裸露到公网；如必须公网访问，建议使用 Nginx/Caddy 等反向代理并启用 HTTPS。
- 设置强管理员密码。
- 固定 `AUTO_CHECK_SECRET_KEY`，并妥善备份 `/var/lib/auto-check`。
- 当前版本是单实例本地文件存储，不要在多台服务器同时写同一份配置和历史数据。
