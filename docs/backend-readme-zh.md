# Student Productivity Agent 后端开发 README

这份 README 面向后端同学，目标不是“讲产品愿景”，而是帮助你们尽快把 `main` 上的 FastAPI 后端做成一版能和当前 `zhaoxun` 前端直接联调的实现。

配套字段契约请同时参考：

- [backend-interface-contract-zh.md](./backend-interface-contract-zh.md)
- [backend-interface-contract.md](./backend-interface-contract.md)

## 1. 当前联调背景

当前真实情况是：

- 前端：`PyQt6` 桌面端
- 后端：`FastAPI`
- 认证：`JWT`
- 前端分支：`zhaoxun`
- 后端参考：`main`

当前前端已经按 `main` 的后端 schema 做过一轮适配，主要对齐了这些点：

- `/api/auth/login`
- `/api/auth/register`
- `/api/auth/logout`
- `/api/dashboard/bootstrap`
- `/api/user/credentials`
- `/api/materials/upload`
- `/api/agent/run`

也就是说，后端现在最重要的不是再重新讨论接口设计，而是尽快把这批接口的实现补上。

## 2. 当前前端到底怎么工作

### 2.1 页面流程

前端当前流程是：

1. `HomePage`
2. `AuthPage`
3. `DashboardPage`

### 2.2 Dashboard 布局

Dashboard 是三栏：

- 左栏：工作区概览、历史对话、资料列表
- 中栏：聊天主窗口
- 右栏：`Thought Trace` + `HITL`

### 2.3 当前不是多页签驱动

这个点很重要。

当前中栏不是早期原型里那种：

- Chat tab
- Schedule tab
- Encyclopedia tab

而是“聊天优先”：

- 用户所有输入都从一个聊天框进入
- `Schedule` 和 `Campus QA` 结果会作为聊天卡片插入
- `Thought Trace` 始终在右栏

所以后端返回的数据，不是给某个独立 tab 用的，而是直接驱动聊天结果流。

### 2.4 模式选择怎么理解

输入框下面现在还有 `Chat / Schedule / Campus QA` 模式按钮。

但当前真实联调里：

- 这个模式主要用于前端 mock 和用户交互提示
- 在 REST 模式下，前端不会再把 `selected_feature` 发给后端
- 路由判断由后端的 agent/router 自己完成

换句话说：

- 不要再按旧文档依赖 `context.selected_feature`
- 现在请按 `backend/schemas/agent.py` 的 `AgentRequest` 来收

## 3. 前端什么时候调什么接口

## 3.1 登录

用户在 `AuthPage` 登录时：

```http
POST /api/auth/login
```

登录成功后，前端会：

1. 保存 JWT token
2. 切到 Dashboard
3. 立刻调用 bootstrap

## 3.2 注册

用户在 `AuthPage` 注册时：

```http
POST /api/auth/register
```

当前前端在 REST 模式下认为：

- 注册成功后会直接拿到 token
- 然后进入已登录状态

## 3.3 进入 Dashboard

进入 Dashboard 后会立刻调：

```http
GET /api/dashboard/bootstrap
Authorization: Bearer <token>
```

这个接口负责把整个主界面初始化起来。

## 3.4 设置页保存 CAS / LLM API Key

设置弹窗现在有两块：

- `CAS`
- `LLM API Key`

保存时分别调：

```http
PUT /api/user/credentials
```

发送体分别是：

```json
{
  "cas_account": "1221xxxx",
  "cas_password": "example-password",
  "llm_api_key": null
}
```

或：

```json
{
  "cas_account": null,
  "cas_password": null,
  "llm_api_key": "sk-example"
}
```

注意：

- 这和前端访问后端的地址无关
- 前端访问后端地址仍然来自 `SPA_API_BASE_URL`
- 设置页里的值是给后端内部调用第三方系统或模型用的

## 3.5 上传资料

左栏点击 `Add Resource` 后：

```http
POST /api/materials/upload
Content-Type: multipart/form-data
```

表单字段名固定：

- `file`

当前前端文件选择器过滤的是：

- `.pdf`
- `.ppt`
- `.pptx`
- `.md`

上传成功后，前端会：

- 把返回的 `file_name` 加到左栏资料列表
- 在 trace 里追加“已加载资料”

## 3.6 发送聊天消息

用户发消息时：

```http
POST /api/agent/run
```

请求体按 `backend/schemas/agent.py`：

```json
{
  "user_id": "u_001",
  "session_id": "sess_ab12cd34",
  "message": "Check whether my Blackboard deadlines conflict with lab time.",
  "attachments": [],
  "hitl_reply": null
}
```

### 3.7 HITL 回执

如果后端返回了 `hitl_request`，前端会弹窗。

用户点击批准 / 拒绝后，前端仍然复用：

```http
POST /api/agent/run
```

这时请求体形态是：

```json
{
  "user_id": "u_001",
  "session_id": "sess_ab12cd34",
  "message": "",
  "attachments": [],
  "hitl_reply": {
    "request_id": "hitl_sess_ab12cd34_001",
    "approved": true
  }
}
```

## 4. 最小可联调实现顺序

如果你们想最短时间把前后端跑起来，我建议严格按这个顺序做：

### 第一步：认证

先实现：

- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/logout`

原因：

- 没 token，后面所有接口都调不起来

### 第二步：bootstrap

实现：

- `GET /api/dashboard/bootstrap`

只要这个接口通了，前端登录后就能真正展示后端返回的：

- 用户信息
- 聊天历史
- 资料列表
- 本地 schedule 缓存

### 第三步：credentials

实现：

- `PUT /api/user/credentials`

这一步通了，设置页就从“本地保存”变成“真实持久化”。

### 第四步：materials upload

实现：

- `POST /api/materials/upload`

这一步通了，左栏资料导入就是真上传，不再只是本地文件列表。

### 第五步：agent/run

实现：

- `POST /api/agent/run`

这一步通了，主聊天、百科卡片、日程卡片、trace、HITL 才会全链路变成真实后端驱动。

## 5. 当前最关键的返回结构要求

## 5.1 bootstrap

`GET /api/dashboard/bootstrap` 必须返回顶层对象，至少含：

```json
{
  "user_profile": {},
  "chat_history": [],
  "materials": [],
  "local_schedule": {
    "events": [],
    "conflicts": []
  }
}
```

注意：

- 不要缺字段
- 没数据时返回空列表 / 空对象，不要返回 `null`

## 5.2 agent/run

`POST /api/agent/run` 必须返回完整 `AgentResponse`：

```json
{
  "session_id": "sess_ab12cd34",
  "assistant_message": {
    "role": "assistant",
    "content": "backend reply",
    "timestamp": "2026-03-23T10:01:00+08:00"
  },
  "trace": [],
  "route": "chat",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": null
  },
  "hitl_request": null,
  "error": null
}
```

当前前端已经支持：

- `route = chat / scheduler / encyclopedia / os_automation`
- `trace.status = pending / running / done / error`

## 6. 当前后端代码里最值得先补的文件

按 `main` 当前目录结构，建议优先看这些文件：

- `backend/api/auth.py`
- `backend/api/dashboard.py`
- `backend/api/user.py`
- `backend/api/materials.py`
- `backend/api/agent.py`
- `backend/schemas/auth.py`
- `backend/schemas/dashboard.py`
- `backend/schemas/user.py`
- `backend/schemas/material.py`
- `backend/schemas/agent.py`

这些文件现在大多已经把接口形状定义好了，只是实现还是 `TODO / NotImplementedError`。

## 7. 本地启动建议

后端本地启动后，前端联调方式建议是：

```bash
export SPA_API_BASE_URL=http://127.0.0.1:8000
python3 frontend/app.py
```

如果不设置这个环境变量，前端会自动退回本地 mock，不会去访问后端。

## 8. 当前最现实的联调完成标准

这版不要求你们一次把所有业务都实现完。

当前最现实的“联调完成”标准是：

1. 用户可以真实登录 / 注册
2. 登录后能真实拉到 bootstrap
3. 设置页能真实保存 CAS / LLM API Key
4. 左栏资料能真实上传
5. 聊天能真实调到 `/api/agent/run`
6. 后端返回的 `trace / ui_payload / hitl_request` 能驱动前端界面变化

做到这一步，当前 `zhaoxun` 前端就已经和 `main` 的后端框架真正接上了。
