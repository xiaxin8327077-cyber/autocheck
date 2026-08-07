# 角色权限：页面查看拆分与列表清理

日期：2026-08-07  
状态：已确认

## 背景

1. 菜单能力与其下功能能力父子联动，取消功能会连带取消菜单。
2. 自定义角色名称旁显示「自定义」，且管理员/普通用户未固定排在前两位。
3. 已下线预留角色删除失败（`system role cannot be deleted`）。

## 方案

### 授权树

仅对「已有功能子项」的末级菜单，将原菜单能力下沉为同级「页面查看」：

- 报送导航：`页面查看`=`menu.report_navigation` + 原功能子项
- 对数历史：`页面查看`=`menu.history` + `history.delete`
- 系统设置：`页面查看`=`sys.settings` + `sys.settings.admin`

不新增能力码；无子功能的末级菜单保持原样。

### 角色列表

- 去掉「自定义」角标
- 排序：admin → user → 其余（按显示名）

### 预留角色删除

- 仅 `admin`/`user` 不可删
- 清理 `role_definitions` 中 `REMOVED_BUILTIN_ROLES` 残留
- `016` SQL 与运行时迁移同步清理
