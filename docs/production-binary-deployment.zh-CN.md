# Auto Check 生产服务器免依赖部署说明

本文说明在生产 Linux 服务器上部署已打包 `auto-check` 可执行文件的完整流程。该方式不要求生产服务器安装 Python、pip 或项目依赖。

## 适用范围

已打包产物适用于常见 Linux x86_64 / amd64 服务器，例如 Ubuntu、Debian、CentOS、Rocky Linux、AlmaLinux 等 64 位 Intel/AMD 架构服务器。

不适用于以下环境：

- Windows
- macOS
- 32 位 Linux
- ARM 架构 Linux，例如 AWS Graviton、鲲鹏 ARM、飞腾 ARM 等

## 一、准备打包产物

生产服务器需要拿到 Linux 可执行文件：

```text
auto-check
```

建议先确认文件类型：

```bash
file auto-check
```

正常应类似：

```text
auto-check: ELF 64-bit LSB executable, x86-64
```

## 二、上传到生产服务器

假设文件已上传到生产服务器：

```text
/tmp/auto-check
```

正式部署目录建议使用：

```text
/opt/auto-check
```

执行：

```bash
sudo mkdir -p /opt/auto-check
sudo cp /tmp/auto-check /opt/auto-check/auto-check
sudo chmod +x /opt/auto-check/auto-check
```

检查文件：

```bash
ls -lh /opt/auto-check/auto-check
```

## 三、创建数据目录

应用自身配置、用户、历史记录、上传文件等本地数据建议统一保存到：

```text
/var/lib/auto-check
```

创建目录：

```bash
sudo mkdir -p /var/lib/auto-check
```

如果服务使用 root 运行，可以保持默认权限：

```bash
sudo chown -R root:root /var/lib/auto-check
```

如果服务使用普通用户运行，例如 `ubuntu`：

```bash
sudo chown -R ubuntu:ubuntu /var/lib/auto-check
```

## 四、创建环境变量配置

创建配置目录：

```bash
sudo mkdir -p /etc/auto-check
```

生成固定密钥：

```bash
openssl rand -hex 32
```

创建环境变量文件：

```bash
sudo tee /etc/auto-check/auto-check.env >/dev/null <<'EOF'
AUTO_CHECK_HOST=0.0.0.0
AUTO_CHECK_PORT=8765
AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json
AUTO_CHECK_NO_BROWSER=1
AUTO_CHECK_SECRET_KEY=请替换为openssl生成的随机密钥
EOF
```

配置说明：

| 配置项 | 说明 |
| --- | --- |
| `AUTO_CHECK_HOST=0.0.0.0` | 监听所有网卡，允许其他机器访问 |
| `AUTO_CHECK_PORT=8765` | 服务端口 |
| `AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json` | 应用配置文件路径 |
| `AUTO_CHECK_NO_BROWSER=1` | 服务器启动时不自动打开浏览器 |
| `AUTO_CHECK_SECRET_KEY=...` | 敏感配置加密密钥 |

`AUTO_CHECK_SECRET_KEY` 一旦用于保存数据库密码等敏感配置，后续迁移、重启或更新时应保持一致，不要随意更换。

检查配置：

```bash
sudo cat /etc/auto-check/auto-check.env
```

## 五、手动启动验证

先手动启动一次，确认可执行文件和配置都正常：

```bash
cd /opt/auto-check

AUTO_CHECK_HOST=0.0.0.0 \
AUTO_CHECK_PORT=8765 \
AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json \
AUTO_CHECK_NO_BROWSER=1 \
AUTO_CHECK_SECRET_KEY=请替换为openssl生成的随机密钥 \
./auto-check
```

服务启动后终端会保持运行。另开一个终端检查：

```bash
curl -I http://127.0.0.1:8765/
```

如果返回 `200 OK`，说明服务正常。

停止手动运行：

```text
Ctrl + C
```

## 六、配置 systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/auto-check
EnvironmentFile=/etc/auto-check/auto-check.env
ExecStart=/opt/auto-check/auto-check
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

如果希望使用普通用户运行，例如 `ubuntu`，服务文件可改为：

```bash
sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/auto-check
EnvironmentFile=/etc/auto-check/auto-check.env
ExecStart=/opt/auto-check/auto-check
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

同时确保目录权限：

```bash
sudo chown -R ubuntu:ubuntu /opt/auto-check /var/lib/auto-check
```

## 七、启动和查看状态

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

看到以下状态说明服务正在运行：

```text
Active: active (running)
```

## 八、访问系统

浏览器访问：

```text
http://服务器IP:8765
```

首次访问后，按页面提示初始化管理员密码，然后配置数据源。

## 九、防火墙和安全组

### Ubuntu / Debian

如果启用了 `ufw`：

```bash
sudo ufw allow 8765/tcp
sudo ufw status
```

### CentOS / Rocky Linux / AlmaLinux

如果使用 `firewalld`：

```bash
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

### 云服务器安全组

云厂商控制台中也需要放行：

```text
TCP 8765
```

如果外部无法访问，但服务器本机 `curl http://127.0.0.1:8765/` 正常，优先检查系统防火墙和云安全组。

## 十、常用运维命令

### 查看服务状态

```bash
sudo systemctl status auto-check --no-pager
```

### 启动服务

```bash
sudo systemctl start auto-check
```

### 停止服务

```bash
sudo systemctl stop auto-check
```

### 重启服务

```bash
sudo systemctl restart auto-check
```

### 查看实时日志

```bash
sudo journalctl -u auto-check -f
```

### 查看最近 100 行日志

```bash
sudo journalctl -u auto-check -n 100 --no-pager
```

### 查看端口监听

```bash
ss -ltnp | grep 8765
```

正常情况下应能看到 `0.0.0.0:8765` 或指定监听地址。

## 十一、更新版本流程

以后拿到新的 `auto-check` 文件后，按以下流程更新。

停止服务：

```bash
sudo systemctl stop auto-check
```

备份旧文件：

```bash
sudo cp /opt/auto-check/auto-check /opt/auto-check/auto-check.bak.$(date +%Y%m%d-%H%M%S)
```

替换新文件，假设新文件在 `/tmp/auto-check`：

```bash
sudo cp /tmp/auto-check /opt/auto-check/auto-check
sudo chmod +x /opt/auto-check/auto-check
```

启动服务：

```bash
sudo systemctl start auto-check
```

检查状态和日志：

```bash
sudo systemctl status auto-check --no-pager
sudo journalctl -u auto-check -n 100 --no-pager
```

## 十二、数据备份和恢复

### 备份

```bash
sudo tar -czf /var/lib/auto-check-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /var/lib auto-check
```

### 恢复

```bash
sudo systemctl stop auto-check
sudo rm -rf /var/lib/auto-check
sudo tar -xzf /var/lib/auto-check-backup-YYYYMMDD-HHMMSS.tar.gz -C /var/lib
sudo systemctl start auto-check
```

## 十三、快速部署命令汇总

以下命令假设新文件已放在 `/tmp/auto-check`：

```bash
sudo mkdir -p /opt/auto-check /var/lib/auto-check /etc/auto-check
sudo cp /tmp/auto-check /opt/auto-check/auto-check
sudo chmod +x /opt/auto-check/auto-check

SECRET_KEY=$(openssl rand -hex 32)

sudo tee /etc/auto-check/auto-check.env >/dev/null <<EOF
AUTO_CHECK_HOST=0.0.0.0
AUTO_CHECK_PORT=8765
AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json
AUTO_CHECK_NO_BROWSER=1
AUTO_CHECK_SECRET_KEY=$SECRET_KEY
EOF

sudo tee /etc/systemd/system/auto-check.service >/dev/null <<'EOF'
[Unit]
Description=Auto Check
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/auto-check
EnvironmentFile=/etc/auto-check/auto-check.env
ExecStart=/opt/auto-check/auto-check
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now auto-check
sudo systemctl status auto-check --no-pager
```

部署完成后访问：

```text
http://服务器IP:8765
```

## 十四、常见问题

### 1. 执行提示 Permission denied

确认文件有执行权限：

```bash
sudo chmod +x /opt/auto-check/auto-check
```

### 2. 启动后无法外部访问

本机检查：

```bash
curl -I http://127.0.0.1:8765/
ss -ltnp | grep 8765
```

如果本机正常，检查：

- `AUTO_CHECK_HOST` 是否为 `0.0.0.0`
- 系统防火墙是否放行 `8765/tcp`
- 云服务器安全组是否放行 `8765/tcp`

### 3. 数据库密码解不开

检查 `AUTO_CHECK_SECRET_KEY` 是否变更：

```bash
sudo grep AUTO_CHECK_SECRET_KEY /etc/auto-check/auto-check.env
```

如果密钥变化，之前保存的加密密码可能无法解密。

### 4. 端口被占用

```bash
sudo ss -ltnp | grep 8765
```

可以修改 `/etc/auto-check/auto-check.env` 中的 `AUTO_CHECK_PORT`，然后重启：

```bash
sudo systemctl restart auto-check
```
