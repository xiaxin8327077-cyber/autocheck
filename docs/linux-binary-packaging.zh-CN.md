# Auto Check Linux 执行文件打包流程

本文说明 Auto Check（监管智核）在 Linux 环境下生成可执行文件的标准流程，覆盖两类产物：

1. **glibc 2.28 兼容包**：使用固定 glibc 版本的 Docker 打包环境生成，推荐用于生产交付。
2. **最新系统包**：在当前 Linux 系统直接打包，适用于打包机和部署服务器系统版本接近的场景。

> 本项目要求 Python 3.12 及以上，打包工具使用 PyInstaller 单文件模式。
>
> Linux 可执行文件不能做到“任意 Linux 都通用”。一般原则是：**用更低 glibc 版本的环境打包，可以运行在相同或更高 glibc 版本的服务器上。**

## 一、产物和目录约定

| 产物类型 | 推荐输出目录 | 推荐文件 | 说明 |
| --- | --- | --- | --- |
| glibc 2.28 兼容包 | `dist-glibc228/` | `auto-check` | 推荐生产交付包，适用于 glibc 2.28 及以上 x86_64 Linux |
| 最新系统包 | `dist/` | `auto-check` | 当前系统直接打包，适用于目标服务器 glibc 不低于打包机的场景 |

东京服务器当前状态页挂载路径：

```text
/var/lib/status-page/uploads/dist-glibc228
```

东京服务器当前最新 glibc 2.28 兼容包：

```text
/opt/auto_check/dist-glibc228/auto-check
```

该文件和状态页挂载目录中的 `auto-check` 当前校验一致：

```text
SHA256: edf1cf16036fe5d25d392996ce6cb1e5758752f52d32727698cb02500fdad861
```

东京服务器当前保留的 Docker 打包相关镜像：

```text
auto-check-linux-build:latest  Python 3.12.9 + PyInstaller 6.21.0 + glibc 2.28
rockylinux:8                   glibc 2.28 基础镜像
```

当前根分区清理后约有 24G 可用空间，足够继续打包 glibc 2.28 兼容包。历史调试镜像已清理，避免 Docker 镜像占满根分区。

> 注意：`auto-check-linux-build:latest` 镜像内自带的 `/output/auto-check` 是镜像构建时产物，不一定等同于 `/opt/auto_check/dist-glibc228/auto-check` 的最新部署产物。正式交付以 `dist-glibc228/auto-check` 及其 `sha256sum` 为准。

## 二、glibc 兼容原则

PyInstaller 单文件包仍会依赖目标系统的 CPU 架构和 glibc 版本。

| 打包环境 | 典型可运行目标 |
| --- | --- |
| glibc 2.28 | glibc 2.28 / 2.31 / 2.34 等 |
| glibc 2.34 | glibc 2.34 及以上，不保证能运行在 2.28 |

建议生产服务器部署前先检查：

```bash
uname -m
getconf GNU_LIBC_VERSION
```

预期架构：

```text
x86_64
glibc 2.28 或更高
```

## 三、Docker 打包方式总览

为了避免每次打包都重新安装系统依赖、重新编译 Python、重新安装 Python 依赖，Docker 打包分成两类：

| 类型 | 用途 | 是否日常使用 |
| --- | --- | --- |
| 当前复用镜像 | 复用东京服务器现有 `auto-check-linux-build:latest`，挂载当前源码并直接执行 PyInstaller | 当前推荐 |
| 标准 builder 镜像 | 只准备可复用打包环境，不复制当前业务源码，不执行打包 | 后续规范化推荐 |
| 一次性 build 镜像 | 从源码开始完整构建并打包，适合追求全量可复现构建 | 可选 |

东京服务器当前日常推荐流程：

```text
复用 auto-check-linux-build:latest → docker run 挂载 /opt/auto_check → 直接 PyInstaller 打包
```

后续日常打包不应再执行：

```bash
pip install -e .[dev]
```

否则每次仍会重复安装 Python 依赖，不符合“复用 Docker 打包环境”的要求。

当前镜像环境验证命令：

```bash
docker run --rm auto-check-linux-build:latest getconf GNU_LIBC_VERSION
docker run --rm auto-check-linux-build:latest python3.12 --version
docker run --rm auto-check-linux-build:latest pyinstaller --version
```

预期：

```text
glibc 2.28
Python 3.12.9
6.21.0
```

## 四、后续规范化：准备可复用 builder 镜像

> 本章是后续规范化方案。东京服务器当前尚未创建 `scripts/Dockerfile.linux-builder`，也没有 `auto-check-builder:glibc228` 镜像；当前日常打包先使用第五章的 `auto-check-linux-build:latest` 流程。

### 1. builder 镜像要求

builder 镜像需要在首次构建时完成以下工作：

1. 基于 glibc 2.28 的 Linux 环境，例如 Rocky Linux 8；
2. 安装系统编译依赖；
3. 源码编译 Python 3.12，并开启 `--enable-shared`；
4. 安装 PyInstaller；
5. 安装本项目全部运行依赖和必要开发依赖；
6. 不复制当前业务源码作为最终打包源码；
7. 不在镜像构建阶段执行 PyInstaller 打包。

### 2. Python 编译关键参数

源码编译 Python 时必须开启 shared library：

```bash
./configure \
  --prefix=/opt/python312 \
  --enable-shared \
  --with-ensurepip=install \
  LDFLAGS='-Wl,-rpath,/opt/python312/lib'
```

`--enable-shared` 很关键。缺少该参数时，PyInstaller 可能报 Python 未启用 shared library。

### 3. builder 镜像内需要预装的 Python 包

builder 镜像内至少需要安装：

```text
pyinstaller
openpyxl
pycryptodomex
py7zr
rarfile
xlrd
psycopg[binary]
PyMySQL
pytest
```

这些依赖来自项目配置和打包需求：

- `openpyxl`：Excel 处理
- `pycryptodomex`：加密能力
- `py7zr`：7z 压缩包解析
- `rarfile`：rar 压缩包解析
- `xlrd`：xls 文件读取
- `psycopg[binary]`：PostgreSQL 驱动
- `PyMySQL`：MySQL 驱动
- `pyinstaller`：打包工具
- `pytest`：打包前测试

### 4. 建议新增 builder Dockerfile

建议新增：

```text
scripts/Dockerfile.linux-builder
```

该文件只负责创建打包环境，不负责打包产物。

示例结构：

```dockerfile
FROM rockylinux:8

RUN dnf install -y epel-release && \
    dnf groupinstall -y "Development Tools" && \
    dnf install -y \
      openssl-devel bzip2-devel libffi-devel \
      readline-devel sqlite-devel zlib-devel \
      xz-devel ncurses-devel gdbm-devel \
      curl tar gzip \
      && dnf clean all

RUN curl -sSL https://www.python.org/ftp/python/3.12.9/Python-3.12.9.tgz -o /tmp/Python.tgz && \
    cd /tmp && tar xzf Python.tgz && \
    cd Python-3.12.9 && \
    ./configure \
      --prefix=/opt/python312 \
      --enable-shared \
      --with-ensurepip=install \
      LDFLAGS='-Wl,-rpath,/opt/python312/lib' && \
    make -j$(nproc) && \
    make install && \
    cd / && rm -rf /tmp/Python.tgz /tmp/Python-3.12.9

ENV PATH=/opt/python312/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/python312/lib:$LD_LIBRARY_PATH

RUN python3.12 -m pip install --upgrade pip && \
    python3.12 -m pip install \
      pyinstaller \
      openpyxl \
      pycryptodomex \
      py7zr \
      rarfile \
      xlrd \
      'psycopg[binary]' \
      PyMySQL \
      pytest

WORKDIR /work
```

### 5. 构建 builder 镜像

在项目根目录执行：

```bash
docker build \
  -f scripts/Dockerfile.linux-builder \
  -t auto-check-builder:glibc228 \
  .
```

### 6. 验证 builder 镜像

```bash
docker run --rm auto-check-builder:glibc228 python3.12 --version
docker run --rm auto-check-builder:glibc228 pyinstaller --version
docker run --rm auto-check-builder:glibc228 getconf GNU_LIBC_VERSION
```

预期：

```text
Python 3.12.x
PyInstaller 6.x
glibc 2.28
```

## 五、日常打包 glibc 2.28 兼容包

东京服务器当前使用现有 `auto-check-linux-build:latest` 镜像作为可复用打包环境。该镜像满足 Python 3.12 + glibc 2.28，并已安装 PyInstaller 和项目运行依赖。

**日常打包命令中不要再执行 `pip install`。**

### 1. 可选：先跑测试

```bash
docker run --rm \
  -v /opt/auto_check:/work \
  -w /work \
  auto-check-linux-build:latest \
  python3.12 -m pytest -q
```

### 2. 执行打包

```bash
cd /opt/auto_check
mkdir -p dist-glibc228 build-glibc228

docker run --rm \
  -v /opt/auto_check:/work \
  -w /work \
  auto-check-linux-build:latest \
  bash -lc '
    pyinstaller --noconfirm --clean --onefile \
      --name auto-check \
      --paths /work/src \
      --add-data "/work/src/auto_check/web:auto_check/web" \
      --add-data "/work/src/auto_check/resources:auto_check/resources" \
      --hidden-import py7zr \
      --hidden-import rarfile \
      --hidden-import psycopg \
      --hidden-import psycopg_binary \
      --hidden-import psycopg.pq \
      --hidden-import pymysql \
      --hidden-import auto_check.resources \
      --hidden-import auto_check.resources.data \
      --distpath /work/dist-glibc228 \
      --workpath /work/build-glibc228 \
      --specpath /work/build-glibc228 \
      /work/src/auto_check/__main__.py
  '
```

输出文件：

```text
/opt/auto_check/dist-glibc228/auto-check
```

生成后同步到状态页挂载目录时，可执行：

```bash
sudo cp /opt/auto_check/dist-glibc228/auto-check /var/lib/status-page/uploads/dist-glibc228/auto-check
sudo chmod +x /var/lib/status-page/uploads/dist-glibc228/auto-check
sha256sum /opt/auto_check/dist-glibc228/auto-check /var/lib/status-page/uploads/dist-glibc228/auto-check
```

### 3. 打包命令要点

| 参数 | 作用 |
| --- | --- |
| `--onefile` | 生成单个可执行文件 |
| `--paths /work/src` | 让 PyInstaller 能找到 `auto_check` 包 |
| `--add-data /work/src/auto_check/web:auto_check/web` | 打入前端静态资源 |
| `--add-data /work/src/auto_check/resources:auto_check/resources` | 打入内置资源文件 |
| `--hidden-import psycopg / psycopg_binary / psycopg.pq` | 打入 PostgreSQL 驱动 |
| `--hidden-import pymysql` | 打入 MySQL 驱动 |
| `--hidden-import py7zr / rarfile` | 打入压缩包解析库 |
| `--hidden-import auto_check.resources / auto_check.resources.data` | 打入资源模块 |

## 六、什么时候需要重建打包镜像

使用当前 `auto-check-linux-build:latest` 流程时，只有以下情况才需要重建或替换打包镜像：

1. `pyproject.toml` 新增、删除或升级依赖；
2. Python 版本变化；
3. PyInstaller 版本需要固定或升级；
4. 目标 glibc 版本变化，例如要支持 glibc 2.17；
5. `scripts/Dockerfile.linux-build` 或后续新增的 `scripts/Dockerfile.linux-builder` 本身变化。

以下情况不需要重建打包镜像：

1. 修改 Python 业务代码；
2. 修改前端页面、样式、脚本；
3. 修改内置资源文件；
4. 修改 README 或普通文档；
5. 重新打同一版本代码。

这些场景直接执行“日常打包 glibc 2.28 兼容包”即可。

### Docker 镜像清理建议

东京服务器根分区空间有限，Docker 镜像应只保留当前必要项：

```text
auto-check-linux-build:latest
rockylinux:8
```

历史调试镜像可以删除，例如：

```text
auto-check-linux-build:glibc228
auto-check-linux-build:glibc228-v2
auto-check-linux-build:glibc228-v3
auto-check-linux-build:glibc228-final
auto-check-linux-build:glibc228-final-v2
auto-check-linux-build:glibc228-clean
auto-check-linux-build:glibc228-am-fix
auto-check-linux-build:am-disambiguation
```

清理前先确认没有容器正在使用相关镜像：

```bash
docker ps -a
docker images
docker system df
```

清理后验证剩余环境：

```bash
df -h /
docker system df
docker run --rm auto-check-linux-build:latest sh -lc 'getconf GNU_LIBC_VERSION && python3.12 --version && pyinstaller --version'
```

## 七、一次性 build 镜像方式（可选）

项目当前已有：

```text
scripts/Dockerfile.linux-build
```

该文件属于“一次性完整构建”方式，通常包含：

```text
构建系统环境 → 编译 Python → 安装依赖 → COPY 当前源码 → PyInstaller 打包
```

这种方式适合做全量可复现构建。东京服务器当前保留的 `auto-check-linux-build:latest` 就来自该路线，但日常重新打包不需要重复 `docker build`，直接使用第五章的挂载源码方式即可。

如果使用该方式：

```bash
docker build \
  -f scripts/Dockerfile.linux-build \
  -t auto-check-linux-build:glibc228 \
  .
```

然后从镜像中导出产物：

```bash
mkdir -p dist-glibc228
container_id=$(docker create auto-check-linux-build:glibc228)
docker cp "$container_id:/output/auto-check" dist-glibc228/auto-check
docker rm "$container_id"
chmod +x dist-glibc228/auto-check
```

注意：该方式在源码变化后通常会重新执行 `COPY . .` 之后的安装和打包步骤，因此不作为日常推荐方式。

## 八、最新系统包打包

如果打包机和部署服务器系统版本接近，无需 Docker，可直接使用项目脚本打包：

```bash
bash scripts/package-linux.sh --clean
```

跳过测试，仅用于临时验证：

```bash
bash scripts/package-linux.sh --clean --skip-tests
```

指定 Python：

```bash
bash scripts/package-linux.sh --clean --python-path /path/to/python3.12
```

输出文件：

```text
dist/auto-check
```

该方式的兼容性取决于打包机 glibc 版本。若部署服务器 glibc 版本低于打包机，可能报：

```text
version `GLIBC_2.xx' not found
```

遇到该问题，应改用 glibc 2.28 兼容包。

## 九、验证产物

### 1. 本机验证

```bash
chmod +x dist-glibc228/auto-check
file dist-glibc228/auto-check
./dist-glibc228/auto-check --help
```

正常输出应包含：

```text
ELF 64-bit LSB executable, x86-64
usage: auto-check [-h] [--host HOST] [--port PORT] [--no-browser] [--config CONFIG]
```

### 2. 目标服务器验证

上传到目标服务器后执行：

```bash
chmod +x auto-check
./auto-check --help
getconf GNU_LIBC_VERSION
```

如果报 glibc 版本错误，说明目标服务器 glibc 版本低于打包环境，需要使用更低 glibc 环境重新打包。

### 3. 生成校验文件

```bash
sha256sum dist-glibc228/auto-check > dist-glibc228/SHA256SUMS.txt
```

目标服务器验证：

```bash
sha256sum -c SHA256SUMS.txt
```

## 十、交付命名建议

建议正式交付时按 glibc 版本和日期命名：

```text
auto-check-linux-x86_64-glibc228-YYYYMMDD
auto-check-linux-x86_64-latest-YYYYMMDD
```

示例：

```bash
cp dist-glibc228/auto-check dist-glibc228/auto-check-linux-x86_64-glibc228-20260701
cp dist/auto-check dist/auto-check-linux-x86_64-latest-20260701
```

## 十一、关于 glibc 2.17

如果目标服务器是 glibc 2.17，需要单独准备 glibc 2.17 的 builder 镜像，例如基于 CentOS 7 或兼容环境。

关键要求不变：

1. 在 glibc 2.17 环境内编译 Python 3.12；
2. Python 编译必须开启 `--enable-shared`；
3. 预装 PyInstaller 和项目依赖；
4. 后续打包仍然采用挂载源码、直接 PyInstaller 的方式。

如果生产环境已经确认 glibc 2.28，则无需再打 glibc 2.17 包。

## 十二、常见问题

### 1. PostgreSQL 连接报 `No module named 'psycopg'`

说明 PostgreSQL 驱动没有被 PyInstaller 打进去。确认打包命令包含：

```text
--hidden-import psycopg
--hidden-import psycopg_binary
--hidden-import psycopg.pq
```

### 2. MySQL 连接失败

确认打包命令包含：

```text
--hidden-import pymysql
```

### 3. 页面空白或静态资源缺失

确认打包命令包含：

```text
--add-data "/work/src/auto_check/web:auto_check/web"
--add-data "/work/src/auto_check/resources:auto_check/resources"
```

### 4. 包体积比之前大

包含 Python 运行时、数据库驱动和压缩包解析库后，Linux 单文件包体积变大是正常现象。

### 5. 是否每次打包都需要 `pip install`

不需要。

正确做法是：首次构建 builder 镜像时安装一次依赖；后续日常打包直接复用 builder 镜像，挂载源码并执行 PyInstaller。

只有项目依赖、Python 版本、PyInstaller 版本、目标 glibc 版本或 builder Dockerfile 变化时，才需要重建 builder 镜像。
