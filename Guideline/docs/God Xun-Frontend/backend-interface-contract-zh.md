# Student Productivity Agent 当前后端接口契约

这份文档描述的是 `zhaoxun` 分支当前前端，如何对接 `main` 分支现有后端框架。

当前真实技术方向：

- 前端：`PyQt6` 桌面端
- 后端：`FastAPI + RESTful API`
- 认证方式：`JWT Bearer Token`
- 运行方式：
  - 不设置 `SPA_API_BASE_URL` 时，前端走本地 mock
  - 设置 `SPA_API_BASE_URL` 后，前端切到真实后端接口

## 1. 当前前端会实际调用哪些接口

当前前端在 REST 模式下会调用这些接口：

1. `POST /api/auth/login`
2. `POST /api/auth/register`
3. `POST /api/auth/logout`
4. `GET /api/dashboard/bootstrap`
5. `PUT /api/user/credentials`
6. `POST /api/materials/upload`
7. `GET /api/materials`
8. `POST /api/schedule/refresh`
9. `GET /api/agent/sessions`
10. `DELETE /api/agent/sessions/{session_id}`
11. `POST /api/agent/run`

当前后端仓库里还有这些接口，但前端这版没有直接主动调用：

- `GET /api/user/profile`
- `PUT /api/user/profile`

## 2. 当前前端界面怎么消费这些接口

### 2.1 页面流转

前端当前流程是：

1. `HomePage`
2. `AuthPage`
3. `DashboardPage`

### 2.2 Dashboard 布局

Dashboard 是三栏：

- 左栏：工作区概览、历史对话、资料列表
- 中栏：聊天主窗口
- 右栏：`Thought Trace` 和 `HITL`

补充说明：

- 输入框下方仍保留 `Chat / Schedule / Campus QA` 模式下拉选择
- 但这只是当前前端的交互引导和 mock 路由
- 在真实后端模式下，前端不会再把 `selected_feature` 发给后端
- 路由判断由后端自己的 agent/router 决定
- 左栏可多选资料；发送消息时，选中的资料会被转成 `attachments`
- 左栏历史对话会在 bootstrap 后继续调用 `GET /api/agent/sessions` 补齐远端会话摘要
- assistant 回复和 trace 在当前前端里会做渐进式渲染，用户看到的是流式体验
- 但当前接口层仍然是普通 JSON 响应，不要求后端已经提供 SSE / WebSocket

### 2.3 前端和后端的职责边界

- 前端负责：
  - 登录 / 注册界面
  - JWT token 持有
  - 聊天、trace、HITL 的展示
  - 文件选择和上传触发
- 后端负责：
  - JWT 认证
  - bootstrap 数据拼装
  - CAS / API Key 持久化
  - materials 上传与向量化
  - agent loop、工具路由、HITL 管理

## 3. 通用约定

### 3.1 协议和格式

- 协议：HTTP
- 风格：RESTful
- 编码：`UTF-8`
- JSON：除上传接口外，统一 `application/json`

### 3.2 认证头

除 `login` / `register` 外，前端在登录成功后会自动带：

```http
Authorization: Bearer <jwt-token>
```

### 3.3 时间格式

建议统一返回 `ISO 8601`，例如：

```text
2026-03-23T10:01:00+08:00
```

### 3.4 前端对错误的处理方式

- 只要后端返回非 `2xx`，前端会把 `detail` 或响应文本显示成错误提示
- 所以建议 FastAPI 的 `HTTPException.detail` 直接返回可读字符串

## 4. 认证接口

## 4.1 `POST /api/auth/login`

### 请求体

```json
{
  "username": "zhaoxun",
  "password": "password123"
}
```

### 返回体

```json
{
  "user_id": "u_001",
  "display_name": "Zhaoxun",
  "major": "Software Engineering",
  "token": "eyJhbGciOi..."
}
```

### 前端用途

- 登录成功后保存 token
- 进入 Dashboard
- 紧接着调用 `GET /api/dashboard/bootstrap`

## 4.2 `POST /api/auth/register`

### 请求体

```json
{
  "username": "zhaoxun",
  "password": "password123",
  "display_name": "Zhaoxun",
  "major": "Software Engineering"
}
```

### 返回体

与 `login` 相同：

```json
{
  "user_id": "u_001",
  "display_name": "Zhaoxun",
  "major": "Software Engineering",
  "token": "eyJhbGciOi..."
}
```

### 前端用途

- 当前前端在 REST 模式下注册成功后，不再走本地 mock
- 会直接进入已登录状态

## 4.3 `POST /api/auth/logout`

### 请求体

```json
{}
```

### 返回体

- 推荐：`204 No Content`

### 前端用途

- 前端会清掉本地 token
- 返回首页

## 5. Dashboard 初始化接口

## 5.1 `GET /api/dashboard/bootstrap`

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 返回体

```json
{
  "user_profile": {
    "user_id": "u_001",
    "display_name": "Zhaoxun",
    "major": "Software Engineering",
    "preferences": {
      "theme": "light",
      "language": "zh"
    }
  },
  "chat_history": [
    {
      "message_id": "msg_001",
      "role": "assistant",
      "content": "Welcome back.",
      "timestamp": "2026-03-23T10:00:00+08:00"
    },
    {
      "message_id": "msg_002",
      "role": "user",
      "content": "Check my schedule this week.",
      "timestamp": "2026-03-23T10:00:30+08:00"
    }
  ],
  "materials": [
    {
      "file_id": "file_101",
      "file_name": "student_handbook_2026.pdf",
      "file_type": "application/pdf",
      "subject_type": "policy",
      "vectorized": true,
      "uploaded_at": "2026-03-23T09:58:00+08:00"
    }
  ],
  "local_schedule": {
    "events": [
      {
        "event_id": "evt_001",
        "title": "CS304 Team Meeting",
        "time": "Mon 19:00 - 20:30",
        "source": "Local TODO",
        "detail": "Finalize API contract and UI handoff."
      }
    ],
    "conflicts": [
      {
        "title": "OOAD report overlaps with lab preparation",
        "detail": "Deadline is 30 minutes before a fixed lab block on Thursday."
      }
    ]
  }
}
```

### 前端用途

- `user_profile`：顶部用户状态和左侧工作区
- `chat_history`：中间聊天区初始化
- `materials`：左侧资料列表
- `local_schedule`：后续 `Schedule` 结果卡片的本地基线数据

### 返回约定

- 不要缺字段
- 没有数据时返回空列表 / 空对象，不要返回 `null`

## 6. 用户凭据接口

## 6.1 `PUT /api/user/credentials`

这个接口是当前设置弹窗的真实落点。

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 请求体

只传需要更新的字段即可：

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

### 返回体

- 推荐：`204 No Content`

### 前端用途

- 设置弹窗里点 `Save CAS` 时，前端会按当前填写情况发送一个或两个 CAS 字段
- 点 `Save API` 时，前端会发 `llm_api_key`
- 如果当前不在 REST 模式，前端只做本地保存，不会调用此接口

## 7. 材料与同步接口

## 7.1 `POST /api/materials/upload`

### 请求头

```http
Authorization: Bearer <jwt-token>
Content-Type: multipart/form-data
```

### 表单字段

- 字段名固定：`file`

### 前端上传行为

- 左侧点击 `Add Resource`
- 选择文件后，前端逐个上传
- 支持的文件过滤目前是：
  - `.pdf`
  - `.ppt`
  - `.pptx`
  - `.md`

### 返回体

```json
{
  "file_id": "file_201",
  "file_name": "uploaded_notes.md",
  "file_type": "text/markdown",
  "subject_type": "cs",
  "vectorized": false,
  "uploaded_at": "2026-03-23T10:02:00+08:00"
}
```

### 前端用途

- 成功后，前端会再调一次 `GET /api/materials`
- 用后端返回的最新 materials 刷新左侧资料列表
- 并在右侧 trace 里追加“已加载资料”

## 7.2 `GET /api/materials`

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 前端用途

- 当前前端会在上传资料成功后调这个接口
- 目的是用后端的真实 materials 列表刷新左侧资料区，而不是只依赖单次上传返回值

## 7.3 `POST /api/schedule/refresh`

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 请求体

```json
{}
```

### 前端用途

- Dashboard 顶部有 `Refresh Schedule` 按钮
- 用户点击后，前端会调这个接口
- 返回的 `events / conflicts` 会直接渲染成聊天里的 `Schedule` 结果卡片

## 7.4 `GET /api/agent/sessions`

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 前端用途

- 登录成功并完成 bootstrap 后，前端会继续调这个接口
- 左栏历史对话会显示远端会话摘要和更新时间
- 当前会话如果还没进入远端列表，前端会暂时保留本地会话项

## 7.5 `DELETE /api/agent/sessions/{session_id}`

### 请求头

```http
Authorization: Bearer <jwt-token>
```

### 前端用途

- 左栏 `Delete Chat` 会调用这个接口
- 只有当前会话已经有真实远端状态时，前端才会请求后端删除
- 删除成功后，前端会把该会话从左栏移除

## 8. Agent 主接口

## 8.1 `POST /api/agent/run`

### 请求头

```http
Authorization: Bearer <jwt-token>
Content-Type: application/json
```

### 普通对话请求体

```json
{
  "user_id": "u_001",
  "session_id": "sess_ab12cd34",
  "message": "Check whether my Blackboard deadlines conflict with lab time.",
  "attachments": [
    {
      "file_id": "file_201",
      "file_name": "uploaded_notes.md",
      "file_type": "text/markdown"
    }
  ],
  "hitl_reply": null
}
```

### HITL 审批回传请求体

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

### 字段说明

- `user_id`：来自登录 / bootstrap
- `session_id`：前端创建并维护，用于区分左侧会话
- `message`：用户输入
- `attachments`：如果用户在左栏选中了资料，前端会把它们转成 `AttachmentRef`
- `attachments`：如果当前没选资料，则会传空数组
- `hitl_reply`：只有在用户点了批准 / 拒绝后才会非空

## 8.2 返回体

```json
{
  "session_id": "sess_ab12cd34",
  "assistant_message": {
    "role": "assistant",
    "content": "I found a conflict on Thursday 16:00. Please review the schedule summary below.",
    "timestamp": "2026-03-23T10:01:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "Read user goal",
      "detail": "Need a schedule conflict check.",
      "status": "done",
      "timestamp": "2026-03-23T10:00:58+08:00"
    }
  ],
  "route": "scheduler",
  "ui_payload": {
    "schedule": {
      "events": [
        {
          "event_id": "evt_002",
          "title": "Blackboard Deadline: OOAD Report",
          "time": "Thu 15:30",
          "source": "Blackboard",
          "detail": "Upload final report before the submission closes."
        }
      ],
      "conflicts": [
        {
          "title": "OOAD report overlaps with lab preparation",
          "detail": "Deadline is 30 minutes before a fixed lab block on Thursday."
        }
      ]
    },
    "encyclopedia": null
  },
  "hitl_request": null,
  "error": null
}
```

### 路由枚举

`route` 只应返回：

- `chat`
- `scheduler`
- `encyclopedia`
- `os_automation`

### trace.status 枚举

当前前端已支持：

- `pending`
- `running`
- `done`
- `error`

### trace.phase 枚举

按当前后端 schema，建议只用：

- `Observation`
- `Reasoning`
- `Tool Use`
- `Reflection`

## 8.3 前端如何消费 `AgentResponse`

- `assistant_message.content`：插入主聊天区
- `trace`：更新右侧 `Thought Trace`
- `ui_payload.schedule`：渲染成聊天里的 `Schedule` 结果卡片
- `ui_payload.encyclopedia`：渲染成聊天里的 `Campus QA` 结果卡片
- `hitl_request`：弹出授权弹窗
- `error`：追加一条 `TraceItemError`

## 8.4 Encyclopedia 响应示例

```json
{
  "session_id": "sess_ab12cd34",
  "assistant_message": {
    "role": "assistant",
    "content": "Here is the handbook answer.",
    "timestamp": "2026-03-23T10:05:00+08:00"
  },
  "trace": [],
  "route": "encyclopedia",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": {
      "query": "credit requirements",
      "answer_markdown": "### Credit Requirement Summary\n- ...",
      "citations": [
        "Student Handbook / Degree Requirements"
      ]
    }
  },
  "hitl_request": null,
  "error": null
}
```

## 8.5 HITL 响应示例

```json
{
  "session_id": "sess_ab12cd34",
  "assistant_message": {
    "role": "assistant",
    "content": "This action requires manual approval before execution.",
    "timestamp": "2026-03-23T10:07:00+08:00"
  },
  "trace": [
    {
      "phase": "Tool Use",
      "title": "Awaiting authorization",
      "detail": "Calendar overwrite is classified as a high-risk action.",
      "status": "pending",
      "timestamp": "2026-03-23T10:07:00+08:00"
    }
  ],
  "route": "os_automation",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": null
  },
  "hitl_request": {
    "request_id": "hitl_sess_ab12cd34_001",
    "action": "Overwrite local study calendar",
    "risk": "high",
    "reason": "The agent wants to move three study blocks to avoid a deadline collision.",
    "payload": [
      "Move OOAD report reminder from Thu 15:00 to Wed 21:00",
      "Create a 40-minute buffer before the Thursday lab"
    ]
  },
  "error": null
}
```

## 9. 当前联调最重要的结论

如果你只想先把前端跑起来，优先保证这 5 条：

1. `login/register` 能返回 `token`
2. `bootstrap` 能返回完整对象且不缺字段
3. `PUT /api/user/credentials` 能正常接收并返回 `204`
4. `POST /api/materials/upload` 能返回 `MaterialInfo`
5. `POST /api/agent/run` 能返回完整的 `AgentResponse`

做到这 5 条，当前 `zhaoxun` 分支前端就能和 `main` 的后端框架跑通主流程。
