# 前端与 API 连接说明

这份文档说明当前 `PyQt6` 前端是如何和后端 `RESTful API` 连接的，适合发给前后端同学一起看。

## 1. 整体结构

当前前端不是网页，而是桌面端：

- 前端：`PyQt6`
- 后端：`FastAPI + RESTful API`
- 通信方式：`HTTP`
- 认证方式：`JWT Bearer Token`

可以把当前结构理解成：

```text
PyQt6 界面
-> app.py 中的按钮/页面逻辑
-> BackendApiClient
-> HTTP 请求
-> FastAPI 后端
-> JSON 响应
-> 前端渲染聊天 / Trace / 结果卡片
```

## 2. API client 在哪里

前端统一通过 [frontend/api_client.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/api_client.py) 访问后端，不在页面代码里直接手写 HTTP。

这个文件里封装了：

- `login`
- `register`
- `logout`
- `bootstrap_dashboard`
- `update_credentials`
- `list_materials`
- `upload_material`
- `run_agent`
- `list_sessions`
- `delete_session`
- `refresh_schedule`

底层统一请求入口是 [frontend/api_client.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/api_client.py) 里的 `_request()`。

它负责：

- 拼接 URL
- 自动加 `Authorization: Bearer <token>`
- 发送 JSON 请求
- 处理 `multipart/form-data` 上传
- 统一解析错误信息

## 3. 前端如何知道后端地址

前端启动时会在 [frontend/app.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/app.py) 里创建：

```python
self.api_client = BackendApiClient.from_env()
```

`BackendApiClient.from_env()` 会读取这些环境变量：

- `SPA_API_BASE_URL`
- `SPA_API_TIMEOUT`
- `SPA_API_TOKEN`

其中最关键的是：

```bash
export SPA_API_BASE_URL=http://127.0.0.1:8000
```

如果没有设置 `SPA_API_BASE_URL`：

- 前端进入本地 `mock mode`
- 不会真的调用后端

如果设置了：

- 前端进入 REST 模式
- 会去调用真实后端接口

## 4. 页面层是怎么调用 API 的

### 4.1 登录

登录按钮绑定到 [frontend/app.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/app.py) 里的 `handle_password_login()`。

流程是：

```text
用户点击 Login
-> handle_password_login()
-> api_client.login(username, password)
-> 保存 token
-> 进入 Dashboard
-> sync_bootstrap_data()
```

对应接口：

- `POST /api/auth/login`
- `GET /api/dashboard/bootstrap`

### 4.2 注册

注册按钮绑定到 `handle_register()`。

流程是：

```text
用户点击 Register
-> handle_register()
-> api_client.register(...)
-> 保存 token
-> 进入 Dashboard
```

对应接口：

- `POST /api/auth/register`

### 4.3 Dashboard 初始化

登录成功后，前端会调用 `sync_bootstrap_data()`。

它会请求：

- `GET /api/dashboard/bootstrap`

这个接口返回：

- `user_profile`
- `chat_history`
- `materials`
- `local_schedule`

前端收到后会分别更新：

- 顶部用户信息
- 左侧资料列表
- 中间聊天区
- 本地日程基线数据

### 4.4 设置页

设置按钮会打开设置弹窗，保存时调用：

- `PUT /api/user/credentials`

现在前端支持保存：

- `CAS account`
- `CAS password`
- `LLM API key`

并且 `CAS` 支持部分更新，不要求账号和密码必须一起填。

### 4.5 上传资料

左侧 `Add Resource` 会触发文件选择器，然后调用：

- `POST /api/materials/upload`

上传成功后，前端还会继续调：

- `GET /api/materials`

这样左栏显示的是后端的真实 materials 列表，不只是本地临时状态。

### 4.6 发送聊天消息

发送按钮会调用 [frontend/app.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/app.py) 里的 `handle_send_message()`，然后进入 `_run_remote_agent()`。

对应接口：

- `POST /api/agent/run`

发送内容包括：

- `user_id`
- `session_id`
- `message`
- `attachments`
- `hitl_reply`

其中：

- `attachments` 来自左侧当前选中的资料
- `hitl_reply` 只在用户处理 HITL 弹窗时才会带

### 4.7 历史会话

前端会在合适时机调用：

- `GET /api/agent/sessions`

作用是同步左侧历史会话列表。

用户删除聊天时会调用：

- `DELETE /api/agent/sessions/{session_id}`

### 4.8 刷新日程

顶部 `Refresh Schedule` 按钮会调用：

- `POST /api/schedule/refresh`

返回的内容会被渲染成聊天里的 `Schedule` 结果卡片。

## 5. Agent 响应是怎么渲染到界面的

后端 `POST /api/agent/run` 返回后，前端会进入 [frontend/app.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/app.py) 里的 `_apply_agent_response()`。

这里主要处理 4 类数据：

- `assistant_message`
- `trace`
- `ui_payload`
- `hitl_request`

它们分别对应：

- `assistant_message` -> 中间聊天消息
- `trace` -> 右侧 `Thought Trace`
- `ui_payload.schedule` -> 聊天里的日程卡片
- `ui_payload.encyclopedia` -> 聊天里的校园问答卡片
- `hitl_request` -> HITL 授权弹窗

## 6. 现在的“流式更新”是怎么做的

当前前端已经支持渐进式展示：

- assistant 回复不是一次性整段出现
- trace 不是一次性全部塞进右栏
- 日程刷新结果也会逐步插入

这部分逻辑在 [frontend/app.py](/Users/darkestbleeding/Desktop/大三下/软件工程/project/frontend/app.py) 里的这些方法：

- `_queue_response_stream()`
- `_advance_response_stream()`
- `_flush_response_stream()`

要注意的是：

- 这是“前端表现层流式”
- 不是 `SSE / WebSocket` 这种网络层真流式

所以当前后端仍然返回普通 JSON 就可以正常工作。

## 7. 当前接口清单

前端当前会实际调用这些接口：

- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/logout`
- `GET /api/dashboard/bootstrap`
- `PUT /api/user/credentials`
- `GET /api/materials`
- `POST /api/materials/upload`
- `POST /api/schedule/refresh`
- `GET /api/agent/sessions`
- `DELETE /api/agent/sessions/{session_id}`
- `POST /api/agent/run`

## 8. 一句话总结

当前前端和后端的连接方式就是：

`PyQt6 页面事件 -> BackendApiClient -> REST API -> JSON 响应 -> 聊天/Trace/结果卡片渲染`

而且现在已经支持：

- JWT 登录态
- 文件上传
- 历史会话同步
- HITL 回执
- 资料附件引用
- 渐进式流式展示
