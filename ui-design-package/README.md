# UI Design 说明

这个文件夹用于存放 `Student Productivity Agent` 前端的 UI design 材料。  
这里的内容是**独立于实际实现代码和运行截图**的设计稿，用来说明系统主要界面的布局、信息组织方式和交互思路。

## 设计目的

这套 UI design 主要服务于课程报告中的 `UI Design` 部分，重点是回答下面几个问题：

- 系统的主要界面有哪些
- 每个界面要展示哪些核心信息
- 用户如何在这些界面中完成主要任务
- 当前前端最终采用了怎样的交互结构

需要注意的是：

- 这些文件不是前端实现代码
- 这些文件也不是直接从运行界面截下来的实现截图
- 它们是基于当前真实前端结构整理出来的低到中保真 wireframe

## 当前前端设计方向

当前前端已经收敛为 `chat-first` 结构，而不是传统的多页面功能导航。

也就是说：

- 主工作区以聊天为中心
- `Schedule` 和 `Campus QA` 不再是完全独立的主页面
- 它们作为结构化结果卡片显示在聊天流中
- `Thought Trace` 常驻在右侧
- `HITL` 和 `Settings` 以弹窗形式覆盖在当前 dashboard 上

这也是为什么这套 UI design 和早期“多页面原型”不同，而是更贴近你现在的真实前端实现。

## 文件说明

### 1. `actual-frontend-dashboard.png`

这是当前真实前端运行后的实际截图，用来辅助对照设计稿和实现效果。  
它不是正式的 UI design 图，而是参考材料。

### 2. `assets/dashboard-wireframe.svg`

主 Dashboard 设计图。  
展示当前前端的三栏结构：

- 左侧：历史对话、资料区、workspace 摘要
- 中间：主聊天区和输入区
- 右侧：Thought Trace

### 3. `assets/scheduler-wireframe.svg`

Schedule 结果设计图。  
这张图表达的是：用户在聊天中选择 `Schedule` 模式后，系统会在聊天流中返回一个结构化的课表/冲突结果卡片，而不是跳转到单独页面。

### 4. `assets/encyclopedia-wireframe.svg`

Campus QA 结果设计图。  
这张图表达的是：用户在聊天中选择 `Campus QA` 模式后，会在聊天流里收到带引用信息的问答结果卡片。

### 5. `assets/hitl-wireframe.svg`

HITL 授权弹窗设计图。  
用于展示高风险操作时的中断式确认流程，包括：

- 风险等级
- 操作摘要
- 原因说明
- 参数预览
- 批准 / 拒绝按钮

### 6. `assets/settings-wireframe.svg`

Settings 弹窗设计图。  
它对应当前前端 Dashboard 顶部的设置入口，重点展示：

- `CAS` 账号密码配置
- `LLM API Key` 配置
- 分区保存按钮

这张图反映的是当前真实前端里的 `SettingsDialog`，不是独立设置页。

## 使用建议

如果要在报告中使用这套材料，建议：

1. 以 `dashboard-wireframe.svg` 作为主图
2. 再补 `scheduler-wireframe.svg` 和 `encyclopedia-wireframe.svg` 说明业务功能
3. 用 `hitl-wireframe.svg` 强调系统安全机制
4. 用 `settings-wireframe.svg` 补充系统配置入口

这样能够比较完整地覆盖你当前前端的主要界面。

## 对应总说明

如果你需要一份更正式、可以直接放进报告正文的说明文档，可以看：

- [ui-design-report.md](/Users/darkestbleeding/Desktop/大三下/软件工程/project/docs/ui-design-report.md)

那个文件更偏“报告正文说明”，而这个 `README.md` 更偏“文件夹说明和使用索引”。
