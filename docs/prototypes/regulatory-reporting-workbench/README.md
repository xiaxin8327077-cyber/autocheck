# 监管报送工作台原型

这是独立的 React / Vite 页面原型，用于报送工作台与调度管理的界面演示。它不属于正式 Auto Check 应用入口，也不使用主应用的 `8765` 端口。

## 开发预览

在本目录安装依赖并启动 Vite：

```powershell
npm install
npm run dev
```

访问终端输出的地址。开发服务器将 `/spoon` 请求代理到 `vite.config.mjs` 配置的 WebSpoon 地址；在线设计器使用同源路径 `/spoon/spoon`。

## 局域网预览

需要 Node.js / npm 和 Python。执行下列命令会先构建静态页面，再启动 Python 预览服务：

```powershell
npm run serve:lan
```

默认监听 `0.0.0.0:8766`，其他电脑使用 `http://<本机局域网IP>:8766/` 访问。服务提供 `dist/client` 静态文件，并将 `/spoon` 请求转发至 WebSpoon；同时处理上游重定向和 Cookie 域，保留同源访问。

Python 预览服务默认使用脚本中的 WebSpoon 地址，可通过环境变量覆盖：

```powershell
$env:SPOON_ORIGIN = 'http://<WebSpoon主机>:8881'
npm run serve:lan
```

`SPOON_ORIGIN` 只用于 Python 预览服务；Vite 开发预览的目标地址在 `vite.config.mjs` 中配置。预览主机需要能够访问实际 WebSpoon 服务。

已有构建时，也可直接启动：

```powershell
python scripts/serve_lan_proxy.py --host 0.0.0.0 --port 8766
```

## 验证命令

```powershell
npm run test:proxy
npm run test:sites
```

代理测试使用本机临时模拟上游，不连接实际 WebSpoon。执行这些命令不会验证正式应用的业务功能。

## 当前改动说明

- 新增局域网预览脚本与代理测试，保留前端单页路由回退。
- WebSpoon iframe 改为同源地址，开发预览和构建后的局域网预览均提供 `/spoon` 代理。
- 调度管理界面使用“版本管理”“提交版本”等通用文案，移除对 SVN 的限定。
- 版本提交、发布与历史恢复仍为原型演示交互，未新增真实版本管理或生产发布后端。

[返回项目首页](../../../README.md)
