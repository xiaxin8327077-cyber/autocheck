# Auto Check 内网生产部署说明

本文适用于在内网生产服务器上部署 `auto-check` Linux 可执行文件。部署方式为：使用已创建好的 `autocheck` 专用用户运行服务，程序、配置、数据均放在 `/home/autocheck` 下，使用 systemd 管理后台服务。

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
