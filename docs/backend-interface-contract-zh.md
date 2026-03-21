# Student Productivity Agent 后端对接说明

这份文档是给后端同学的中文联调说明，目标是把当前前端需要的接口、字段含义、返回格式和联调注意事项一次讲清楚。

当前项目技术方向已经固定为：

- 前端：`PyQt6 / PySide6` 桌面端
- 后端：`RESTful API`
- 当前前端默认可跑本地 mock，但已经支持切换到真实 REST 接口

对于当前里程碑，前后端只需要先对接 2 个核心接口：

1. `GET /api/dashboard/bootstrap`
2. `POST /api/agent/run`

这样就足够支撑以下前端区域：

- 主页后的登录与主界面进入流程
- 主聊天区
- `Thought Trace` 面板
- 聊天中的 `Schedule` 结果卡片
- 聊天中的 `Campus QA` 结果卡片
- `HITL` 授权弹窗
- 左侧用户资料与材料列表

## 1. 前端当前长什么样

前端当前的页面流转是：

1. `HomePage`
2. `AuthPage`（登录 / 注册）
3. `DashboardPage`

其中 `DashboardPage` 由三部分组成：

- 左侧：历史对话、资料列表、工作区概览
- 中间：主聊天区
- 右侧：`Thought Trace` + `HITL` 授权入口

补充说明：

- 当前中间聊天区只有一个输入入口
- 输入框下方有模式选择入口
- 用户可显式选择：
  - `Chat`
  - `Schedule`
  - `Campus QA`
- `Schedule` 和 `Campus QA` 的结果会直接插入聊天流里，而不是依赖独立页签

也就是说，后端返回的数据不是给某一个小组件用的，而是要同时驱动聊天、思维追踪、日程、百科和授权弹窗。

## 2. 总体接口设计原则

### 2.1 为什么只先要两个接口

当前阶段我们故意把接口压得很小，原因是：

- 前端先要能跑通主流程，而不是把接口拆得特别细
- AI loop 本身天然适合统一承接“用户输入 -> 推理 -> 工具 -> 结果回传”
- 页面初始化也适合通过一个 bootstrap 接口一次性加载

所以当前建议分工是：

- `bootstrap` 负责“初始化页面”
- `agent/run` 负责“处理用户动作”

### 2.2 当前不要求的部分

下面这些可以后面再拆，不是这一版必须项：

- 单独文件上传接口
- 单独百科查询接口
- 单独 schedule 刷新接口
- 单独 HITL 审批接口
- 单独 trace 拉流接口
- 登录 / 注册真实后端接口

说明：

- 现在前端里的登录 / 注册仍然是本地原型逻辑
- 也就是说，本轮联调先不用被认证系统卡住
- 真正需要后端先提供的是“主界面初始化”和“AI loop 返回”

## 3. 通用约定

## 3.1 请求与返回

- 协议：HTTP
- 风格：RESTful
- 数据格式：`application/json`
- 字符编码：`UTF-8`

## 3.2 时间格式

统一用 `ISO 8601`，例如：

```text
2026-03-21T20:00:00+08:00
```

## 3.3 枚举值约定

### `trace.status`

只能是：

- `done`
- `running`
- `pending`

### `route`

只能是：

- `chat`
- `scheduler`
- `encyclopedia`

### `hitl_request.risk`

建议只用：

- `low`
- `medium`
- `high`

### `assistant_message.role`

当前前端只关心助手消息，因此推荐固定返回：

- `assistant`

### `chat_history.role`

只能是：

- `user`
- `assistant`

## 3.4 多语言约定

前端本身已经支持中英文 UI 切换，但当前后端接口里的正文内容先不强制要求双语。

当前建议：

- `trace.title`
- `trace.detail`
- `assistant_message.content`
- `ui_payload.*`
- `hitl_request.*`

这些字段先返回单语字符串即可，优先保证结构稳定。

如果后端后续要支持真正的双语内容，可以再统一升级字段结构；当前阶段不建议过早把接口设计成双语嵌套对象。

## 4. 接口一：Dashboard Bootstrap

## 4.1 Endpoint

```http
GET /api/dashboard/bootstrap?user_id=u_001
```

## 4.2 作用

前端进入主界面后，会调用这个接口一次性拿到页面初始化数据。

这个接口负责返回：

- 用户资料
- 聊天历史
- 材料列表
- 本地日程缓存

## 4.3 Query 参数

### `user_id`

- 类型：`string`
- 必填：是
- 含义：当前用户唯一标识

说明：

- 当前前端原型里，`user_id` 可以先直接用用户名代替
- 后续如果你们接正式认证，再换成数据库里的真正用户 ID 即可

## 4.4 返回结构

```json
{
  "user_profile": {
    "user_id": "u_001",
    "display_name": "SUSTech Student",
    "major": "Software Engineering",
    "preferences": {
      "theme": "cosmic",
      "language": "en"
    }
  },
  "chat_history": [
    {
      "message_id": "msg_001",
      "role": "assistant",
      "content": "Welcome back. I can track your schedule, search campus policies, and explain each tool step in the Thought Trace panel.",
      "timestamp": "2026-03-21T19:50:00+08:00"
    },
    {
      "message_id": "msg_002",
      "role": "user",
      "content": "Please check whether my Blackboard deadlines conflict with lab time.",
      "timestamp": "2026-03-21T19:51:00+08:00"
    }
  ],
  "materials": [
    {
      "file_id": "file_101",
      "file_name": "week5_notes.md",
      "file_type": "text/markdown",
      "vectorized": false,
      "uploaded_at": "2026-03-21T18:00:00+08:00"
    },
    {
      "file_id": "file_102",
      "file_name": "student_handbook_2026.pdf",
      "file_type": "application/pdf",
      "vectorized": true,
      "uploaded_at": "2026-03-20T21:00:00+08:00"
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

## 4.5 字段说明

### `user_profile`

用于左侧用户卡片和顶部状态栏。

推荐字段：

- `user_id`: 用户 ID
- `display_name`: 界面显示名
- `major`: 专业
- `preferences`: 可选配置

当前前端实际会直接消费：

- `display_name`
- `major`

### `chat_history`

用于初始化主聊天区。

每条消息至少要有：

- `role`
- `content`

其余字段如：

- `message_id`
- `timestamp`

可以作为后续扩展保留。

### `materials`

用于左侧材料列表。

当前前端至少会读取：

- `file_name`

所以如果后端已经有文件表，最少只要保证 `file_name` 存在即可。

### `local_schedule`

这是一个对象，不是数组。

结构必须是：

```json
{
  "events": [],
  "conflicts": []
}
```

其中：

- `events` 给日程列表
- `conflicts` 给冲突提醒卡片

### `local_schedule.events[]`

每一项建议包含：

- `title`
- `time`
- `source`
- `detail`

### `local_schedule.conflicts[]`

每一项建议包含：

- `title`
- `detail`

## 4.6 前端消费方式

这个接口的数据会映射到：

- 左侧资料卡：`user_profile`
- 左侧材料列表：`materials`
- 中间聊天历史：`chat_history`
- 日程能力的本地缓存：`local_schedule.events`
- 日程能力的冲突缓存：`local_schedule.conflicts`

## 4.7 推荐实现建议

- 哪怕某一块数据暂时没有，也尽量返回空数组 / 空对象，而不是缺字段
- 推荐保证这些 key 始终存在：
  - `user_profile`
  - `chat_history`
  - `materials`
  - `local_schedule`
- `local_schedule` 即使没有内容，也建议返回：

```json
{
  "events": [],
  "conflicts": []
}
```

## 5. 接口二：AI Loop Run

## 5.1 Endpoint

```http
POST /api/agent/run
```

## 5.2 作用

这个接口负责承接前端的用户动作，并把 AI loop 的结果一次性返回给前端。

你可以把它理解为：

- 前端发一个“用户请求”
- 后端完成推理 / 路由 / 调工具 / 生成结果
- 把界面需要的所有数据一次回传

## 5.3 它负责什么

这个接口当前同时负责：

- 主聊天回复
- `Thought Trace`
- 日程结果
- 校园百科结果
- `HITL` 拦截
- `HITL` 审批回传

也就是说，对前端来说这是一个总入口。

## 5.4 请求体

```json
{
  "user_id": "u_001",
  "session_id": "sess_20260321_01",
  "message": "Check whether my Blackboard deadlines conflict with lab time.",
  "attachments": [
    {
      "file_id": "file_101",
      "file_name": "week5_notes.md",
      "file_type": "text/markdown"
    }
  ],
  "context": {
    "active_tab": "chat",
    "selected_feature": "scheduler"
  },
  "hitl_reply": null,
  "connection_settings": {
    "cas": {
      "username": "1221xxxx",
      "password": "example-password"
    },
    "api": {
      "base_url": "https://api.example.com",
      "api_key": "example-api-key"
    }
  }
}
```

## 5.5 请求字段说明

### `user_id`

- 类型：`string`
- 必填：是
- 含义：当前用户 ID

### `session_id`

- 类型：`string`
- 必填：是
- 含义：当前会话 ID

说明：

- 前端会在应用运行时维持一个 `session_id`
- 后端建议把它作为上下文串联标识

### `message`

- 类型：`string`
- 必填：是
- 含义：用户这一次的自然语言输入

注意：

- 如果是用户在审批 `HITL`，这里可以是空字符串

### `attachments`

- 类型：`array`
- 必填：否
- 含义：这次请求附带的文件

当前前端还没有真实上传流，但字段已经预留好了。

### `context.active_tab`

当前前端固定传 `chat`，因为主工作区现在是聊天优先布局。

可选值建议：

- `chat`

### `context.selected_feature`

用于告诉后端，这次输入更偏向哪类功能。

当前前端会发这些值：

- `agent_chat`
- `scheduler`
- `encyclopedia`
- `os_automation`

说明：

- `agent_chat / scheduler / encyclopedia` 来自输入框下方的模式选择
- `os_automation` 主要用于高风险动作和 HITL 继续执行流程

### `hitl_reply`

如果本次请求是对先前高风险操作的审批，则这里不为 `null`。

格式如下：

```json
{
  "request_id": "hitl_9001",
  "approved": true
}
```

### `connection_settings`

这是一个可选字段。

作用是：

- 前端把用户在设置页中填写的 `CAS` 和 `API` 配置先保存在本地会话中
- 当用户发起 `agent/run` 请求时，再把这些配置一起转交给后端

推荐结构：

```json
{
  "cas": {
    "username": "1221xxxx",
    "password": "example-password"
  },
  "api": {
    "base_url": "https://api.example.com",
    "api_key": "example-api-key"
  }
}
```

说明：

- 如果某一项还没配置，可以不传，或者传 `null`
- 前端不会直接使用这些配置去连接服务，只负责保存和转发
- 后端收到后，自行决定是否用于 Blackboard、CAS 登录、LLM / 第三方 API 调用等流程

## 5.6 普通请求返回结构

```json
{
  "session_id": "sess_20260321_01",
  "assistant_message": {
    "role": "assistant",
    "content": "I found a conflict on Thursday 16:00. Please review the schedule summary rendered in chat.",
    "timestamp": "2026-03-21T20:00:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "Read user goal",
      "detail": "Need a schedule conflict check and concise explanation.",
      "status": "done",
      "timestamp": "2026-03-21T19:59:58+08:00"
    },
    {
      "phase": "Reasoning",
      "title": "Plan tool sequence",
      "detail": "Blackboard scraper -> merge local calendar -> detect overlap.",
      "status": "done",
      "timestamp": "2026-03-21T19:59:59+08:00"
    }
  ],
  "route": "scheduler",
  "ui_payload": {
    "schedule": {
      "events": [
        {
          "title": "Blackboard Deadline: OOAD Report",
          "time": "Thu 15:30",
          "source": "Blackboard",
          "detail": "Upload final report before the submission closes."
        },
        {
          "title": "Embedded Systems Lab",
          "time": "Thu 16:00 - 18:00",
          "source": "Campus Calendar",
          "detail": "Lab room 107, attendance required."
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

## 5.7 返回字段说明

### `assistant_message`

这是主聊天区要显示的内容。

当前前端至少使用：

- `assistant_message.content`

### `trace`

这是右侧 `Thought Trace` 面板的数据源。

每一项建议包含：

- `phase`
- `title`
- `detail`
- `status`

时间戳可以带，也可以不带；前端当前不会渲染时间戳，但保留对后续有帮助。

### `route`

用于告诉前端，这次回复更偏向哪类能力结果。

可选值：

- `chat`
- `scheduler`
- `encyclopedia`

前端当前行为：

- `scheduler`：在主聊天区插入日程结果卡片
- `encyclopedia`：在主聊天区插入校园问答结果卡片
- 其他：作为普通聊天回复处理

### `ui_payload`

这是专门给界面消费的结构化数据。

当前建议始终返回：

```json
{
  "schedule": null,
  "encyclopedia": null
}
```

如果某一块没有数据，就给 `null`。

### `ui_payload.schedule`

如果 route 指向日程，或本次请求产生日程数据，就填这个对象。

结构：

```json
{
  "events": [],
  "conflicts": []
}
```

### `ui_payload.encyclopedia`

如果本次请求产出校园百科结果，就填这个对象。

结构建议：

```json
{
  "query": "credit requirements",
  "answer_markdown": "### Credit Requirement Summary\n- ...",
  "citations": [
    "Student Handbook / Degree Requirements / General Rules"
  ]
}
```

说明：

- `answer_markdown` 给聊天中的 markdown 结果卡片
- `citations` 给同一张聊天结果卡片里的引用区域

### `hitl_request`

如果本次动作被后端识别为高风险操作，就不要直接执行，而是返回 `hitl_request`。

## 5.8 Encyclopedia 返回示例

```json
{
  "session_id": "sess_20260321_01",
  "assistant_message": {
    "role": "assistant",
    "content": "Here is the handbook-based answer with citations.",
    "timestamp": "2026-03-21T20:10:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "Recognized campus policy query",
      "detail": "Routed to handbook retrieval pipeline.",
      "status": "done",
      "timestamp": "2026-03-21T20:09:59+08:00"
    }
  ],
  "route": "encyclopedia",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": {
      "query": "credit requirements",
      "answer_markdown": "### Credit Requirement Summary\n- Undergraduate students must complete the program credit minimum.",
      "citations": [
        "Student Handbook / Degree Requirements / General Rules"
      ]
    }
  },
  "hitl_request": null,
  "error": null
}
```

## 5.9 HITL 拦截返回示例

```json
{
  "session_id": "sess_20260321_01",
  "assistant_message": {
    "role": "assistant",
    "content": "This action requires manual approval before execution.",
    "timestamp": "2026-03-21T20:05:00+08:00"
  },
  "trace": [
    {
      "phase": "Tool Use",
      "title": "Awaiting authorization",
      "detail": "Calendar overwrite is classified as a high-risk action.",
      "status": "pending",
      "timestamp": "2026-03-21T20:05:00+08:00"
    }
  ],
  "route": "chat",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": null
  },
  "hitl_request": {
    "request_id": "hitl_9001",
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

## 5.10 HITL 审批回传示例

当前前端会复用同一个接口，把审批结果再发回去：

```json
{
  "user_id": "u_001",
  "session_id": "sess_20260321_01",
  "message": "",
  "attachments": [],
  "context": {
    "active_tab": "chat",
    "selected_feature": "os_automation"
  },
  "hitl_reply": {
    "request_id": "hitl_9001",
    "approved": true
  }
}
```

后端收到后建议：

1. 根据 `request_id` 找到对应待审批动作
2. 判断 `approved`
3. 如果批准，则继续执行或继续规划
4. 再把新的 `assistant_message`、`trace`、`ui_payload` 返回给前端

## 5.11 前端消费方式

这个接口返回的数据在前端里的映射关系如下：

- `assistant_message.content` -> 主聊天区
- `trace[]` -> 右侧 Thought Trace
- `route` -> 标记本次结果更偏向哪种能力
- `ui_payload.schedule` -> 聊天中的日程结果卡片
- `ui_payload.encyclopedia` -> 聊天中的校园问答结果卡片
- `hitl_request` -> 授权弹窗

## 6. 错误处理建议

## 6.1 推荐保留 `error` 字段

建议所有返回都保留：

```json
{
  "error": null
}
```

当发生业务错误时，可以写成：

```json
{
  "error": {
    "code": "RAG_TIMEOUT",
    "message": "Vector retrieval timed out.",
    "retryable": true
  }
}
```

说明：

- 当前前端对 `error` 的 UI 展示还比较轻
- 但这个字段非常适合后续扩展，不建议省掉

## 6.2 HTTP 状态码建议

- `200`: 请求成功，哪怕业务上返回了 `hitl_request`
- `400`: 参数错误
- `404`: 资源不存在
- `500`: 后端内部错误
- `503`: 外部工具服务不可用

## 7. 当前前端实际联调方式

当前前端已经支持通过环境变量连接真实后端：

```bash
export SPA_API_BASE_URL=http://127.0.0.1:8000
python3 frontend/app.py
```

联调行为如下：

1. 用户登录成功后
   前端调用 `GET /api/dashboard/bootstrap`

2. 用户在聊天框发消息
   前端调用 `POST /api/agent/run`

3. 用户在聊天输入区切换到 `Schedule` 或 `Campus QA` 模式后发消息
   前端也调用 `POST /api/agent/run`

4. 后端如果返回 `hitl_request`
   前端会弹出授权框

5. 用户点击同意 / 拒绝
   前端再次调用 `POST /api/agent/run`，带上 `hitl_reply`

## 8. 推荐后端实现顺序

如果你们想最快联通，建议按下面顺序做：

### 第一步

先做 `GET /api/dashboard/bootstrap`

哪怕先返回静态数据也没关系，只要结构稳定，前端就能先把主界面吃起来。

### 第二步

做 `POST /api/agent/run` 的最小返回版本：

- `assistant_message`
- `trace`
- `route`
- `ui_payload`
- `hitl_request: null`

这样前端聊天、百科、日程切页就能先联通。

### 第三步

再补 `hitl_request`

这样高风险操作弹窗也能跑起来。

### 第四步

最后再让 `ui_payload.schedule` 和 `ui_payload.encyclopedia` 真正接你们的工具链和 RAG。

## 9. curl 联调示例

## 9.1 bootstrap

```bash
curl "http://127.0.0.1:8000/api/dashboard/bootstrap?user_id=student"
```

## 9.2 普通 agent 请求

```bash
curl -X POST "http://127.0.0.1:8000/api/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "student",
    "session_id": "sess_demo_001",
    "message": "check credit requirements",
    "attachments": [],
    "context": {
      "active_tab": "chat",
      "selected_feature": "encyclopedia"
    },
    "hitl_reply": null,
    "connection_settings": {
      "cas": {
        "username": "1221xxxx",
        "password": "example-password"
      },
      "api": {
        "base_url": "https://api.example.com",
        "api_key": "example-api-key"
      }
    }
  }'
```

## 9.3 HITL 审批回传

```bash
curl -X POST "http://127.0.0.1:8000/api/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "student",
    "session_id": "sess_demo_001",
    "message": "",
    "attachments": [],
    "context": {
      "active_tab": "chat",
      "selected_feature": "os_automation"
    },
    "connection_settings": {
      "cas": {
        "username": "1221xxxx",
        "password": "example-password"
      },
      "api": {
        "base_url": "https://api.example.com",
        "api_key": "example-api-key"
      }
    },
    "hitl_reply": {
      "request_id": "hitl_9001",
      "approved": true
    }
  }'
```

## 10. 后端联调检查清单

后端同学可以按这个清单自查：

- `bootstrap` 是否一定返回 `user_profile / chat_history / materials / local_schedule`
- `local_schedule` 是否是对象而不是数组
- `local_schedule.events` 和 `local_schedule.conflicts` 是否字段齐全
- `agent/run` 是否一定返回 `assistant_message / trace / route / ui_payload / hitl_request / error`
- `trace.status` 是否只使用 `done / running / pending`
- `route` 是否只使用 `chat / scheduler / encyclopedia`
- `hitl_request` 是否包含 `request_id / action / risk / reason / payload`
- `ui_payload.encyclopedia.answer_markdown` 是否真的是 markdown 字符串
- 所有时间字段是否统一使用 `ISO 8601`

## 11. 当前最重要的结论

如果后端现在时间有限，先保证下面两件事就够前端联调：

1. `GET /api/dashboard/bootstrap` 返回结构稳定
2. `POST /api/agent/run` 返回结构稳定

只要这两件事稳定了，前端这边的：

- 聊天
- Trace
- 日程
- 百科
- HITL

就都能跟着接起来。
