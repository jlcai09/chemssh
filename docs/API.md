# chemweb API 与窗口交互指南

本文档面向后续维护者和 coding agent。目标是让新模块可以快速接入 chemweb 的后端接口、文件管理器、终端、预览器和队列窗口。

所有后端接口都以 `/api` 开头。错误统一返回：

```json
{
  "success": false,
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "File not found"
  }
}
```

前端请求封装在 `frontend/src/api/` 下。新增模块优先复用这些封装，不要在组件里手写重复的 `fetch` 错误处理。

## 系统信息

### `GET /api/system/info`

返回当前运行环境、项目版本、调度器类型和工作区根目录。

```json
{
  "project_version": "0.1.0",
  "username": "user",
  "hostname": "node01",
  "cwd": "/home/user/project",
  "python_version": "3.12.7",
  "scheduler": "slurm",
  "workspace_root": "/home/user"
}
```

前端类型与封装：`frontend/src/api/system.ts`。

### `GET /api/system/identity`

返回当前服务的轻量身份信息。`chemweb` CLI 启动前会用此接口判断目标端口是否已由可复用的 Chemweb 服务占用。

```json
{
  "app": "chemweb",
  "project_version": "0.2.0",
  "pid": 12345,
  "scheduler": "slurm",
  "workspace_root": "/home/user"
}
```

启动复用规则：

- 端口未占用：正常启动新服务。
- 端口占用且 `/api/system/identity` 返回 `app="chemweb"`：默认仅当 `workspace_root` 与当前配置一致时复用已有服务。
- 端口占用但不是 Chemweb，或无法读取身份信息：启动失败并报告端口占用。

CLI 参数：

- `--reuse-existing auto`：默认值，复用同工作区的已有 Chemweb 服务。
- `--reuse-existing never`：不复用已有服务；端口已占用时直接失败。
- `--reuse-existing any-chemweb`：复用该端口上的任意 Chemweb 服务，即使工作区不同。
- `--check-port`：只检测目标端口并退出，不启动服务。端口空闲或可复用时退出码为 `0`；端口被不可复用服务占用时退出码为 `1`。

## 文件管理

文件路径必须在 `workspace.root` 内。后端会解析绝对路径并阻止越界访问。

### `GET /api/files/list?path=/workspace/project`

列出目录内容。省略 `path` 时列出工作区根目录。

响应：

```json
{
  "path": "/workspace/project",
  "parent": "/workspace",
  "items": [
    {
      "name": "mol.xyz",
      "path": "/workspace/project/mol.xyz",
      "type": "file",
      "size": 128,
      "mtime": "2026-05-25T10:00:00",
      "extension": ".xyz",
      "preview_type": "structure",
      "format": "xyz"
    }
  ]
}
```

### `GET /api/files/read?path=/workspace/project/input.inp&force=false`

读取文本预览。默认大小上限由 `workspace.max_read_size_mb` 控制。遇到大文件时返回 `FILE_TOO_LARGE`，用户确认后前端可用 `force=true` 重试。

### `POST /api/files/write`

保存文本文件。

```json
{
  "path": "/workspace/project/input.inp",
  "content": "..."
}
```

### `POST /api/files/mkdir`

新建目录。

```json
{
  "path": "/workspace/project",
  "name": "new_case"
}
```

### `POST /api/files/upload`

上传文件，使用 multipart 表单：

- `path`: 目标目录。
- `file`: 上传文件。

### `GET /api/files/download?path=/workspace/project/result.out`

下载单个文件。路径必须指向文件，目录会返回 `NOT_A_FILE`。

### `POST /api/files/download-archive`

将多个文件或目录打包为 `chemweb-selection.zip`。工具栏“下载”使用此接口。

```json
{
  "paths": [
    "/workspace/project/result.out",
    "/workspace/project/case_dir"
  ]
}
```

### `GET /api/files/download-selection?path=/a&path=/b`

拖拽下载专用 GET 接口。单个普通文件会直接返回文件；多个路径或目录会返回 zip。文件管理器拖到浏览器外部时会把该接口写入 `text/uri-list`，浏览器打开该 URL 即可下载。

### `DELETE /api/files/delete?path=/workspace/project/old.log`

删除文件或目录。仅当 `workspace.allow_delete=true` 可用。

### `POST /api/files/rename`

重命名文件或目录。

```json
{
  "old_path": "/workspace/project/a.xyz",
  "new_path": "/workspace/project/b.xyz"
}
```

### `GET /api/files/tail?path=/workspace/project/slurm-123.out&lines=300`

读取日志类文件末尾 N 行，适合 `.log`、`.out`、`slurm-*.out`、`OUTCAR`、`OSZICAR` 等。

前端封装：`frontend/src/api/files.ts`。

## 结构预览

### `GET /api/structures/ase/preview?path=/workspace/project/mol.xyz&force=false`

读取结构摘要和初始帧。大文件会返回 `STRUCTURE_FILE_TOO_LARGE`，用户确认后前端可用 `force=true` 重试。

### `GET /api/structures/ase/frame?path=/workspace/project/mol.xyz&index=0&force=false`

按索引读取单帧结构。

### `GET /api/structures/ase/frames.bin?path=/workspace/project/traj.xyz&start=0&count=64&force=false`

读取轨迹二进制帧块。

支持格式由 `backend/app/services/file_types.py` 与 ASE 能力共同决定。当前常见格式包括 `xyz`、`extxyz`、`traj`、`pdb`、`mol`、`sdf`、`cif`、`db`，并强制识别 `POSCAR`、`CONTCAR`、`XDATCAR`、`OUTCAR` 等 VASP 文件名。

前端封装：`frontend/src/api/structures.ts`。

`frontend/src/api/structures.ts` 也提供通用 `StructureSource` 版本的读取函数。ASE 是默认数据源：

```json
{
  "id": "ase",
  "parser": "ase",
  "apiBase": "/api/structures/ase"
}
```

插件如果提供兼容结构接口，可以注册自己的 `StructureSource`，并复用现有预览窗口和 `MoleculeViewer`。兼容接口包括：

- `GET {apiBase}/preview`
- `GET {apiBase}/frame`
- `GET {apiBase}/frames`
- `GET {apiBase}/frames.bin`

`frames.bin` 继续使用 `application/vnd.chemweb.structure+bin`，由现有 Brotli middleware 自动压缩。

## 插件

插件目录默认扫描项目根目录下的 `plugins/`。扫描阶段只读取 `chemweb-plugin.json`，不会导入插件后端或加载插件 UI。用户从工作区右侧功能区的 `+` 菜单打开插件面板后，前端才调用激活接口。

### `GET /api/plugins`

返回已扫描到的插件清单和面板声明。

```json
{
  "plugins": [
    {
      "id": "cclib",
      "name": "cclib",
      "version": "0.1.0",
      "description": "Parse quantum chemistry output files with cclib and send structure data to the existing preview window.",
      "panels": [
        {
          "id": "cclib-provider",
          "title": "cclib",
          "kind": "tool",
          "singleton": true
        }
      ],
      "active": false
    }
  ]
}
```

前端封装：`frontend/src/api/plugins.ts`。

### `POST /api/plugins/{plugin_id}/activate`

激活插件。宿主会按需导入插件后端入口，挂载插件 API，并返回前端资源和 API 前缀。

```json
{
  "id": "cclib",
  "active": true,
  "asset_url": "/api/plugins/cclib/assets",
  "api_base": "/api/plugins/cclib/api",
  "panels": [],
  "file_manager": {}
}
```

### `POST /api/plugins/{plugin_id}/deactivate`

通知插件停用。当前实现会调用插件的 `on_deactivate()` 钩子，并让前端注销该插件注册的文件预览 provider。

### `GET /api/plugins/{plugin_id}/dependencies`

返回插件 Python 依赖状态。宿主会读取插件清单与插件状态文件，报告当前有效依赖模式、Python 解释器、requirements 路径、已安装包和缺失包。

```json
{
  "plugin_id": "cclib",
  "python": {
    "mode": "host",
    "manifest_mode": "host",
    "python": "D:/Git/chemweb/.venv/Scripts/python.exe",
    "requirements": "D:/Git/chemweb/plugins/cclib/backend/requirements.txt",
    "packages": [
      { "name": "cclib", "version": "1.8.1" }
    ],
    "missing": [],
    "satisfied": true
  }
}
```

### `POST /api/plugins/{plugin_id}/dependencies/install`

安装插件 Python 依赖。请求体：

```json
{
  "mode": "host"
}
```

或：

```json
{
  "mode": "venv",
  "venv": ".venv"
}
```

`host` 会修改运行 chemweb 的当前 Python 环境；`venv` 会创建或复用插件目录内的虚拟环境。安装结果会写入插件状态文件，不改写插件清单。

### `POST /api/plugins/{plugin_id}/dependencies/external`

保存并校验外部 Python 解释器路径：

```json
{
  "python": "D:/envs/cclib/python.exe"
}
```

该接口只验证解释器可运行并保存配置；需要 external 执行能力的插件应在自己的后端实现里读取该配置。

### `GET /api/plugins/{plugin_id}/assets/{path}`

读取插件已构建的前端静态资源。`GET /api/plugins/{plugin_id}/assets` 默认返回插件入口 `index.html`。
随插件发布且不需要构建的前端资源推荐放在 `frontend/bundle/`，并在清单中使用 `dependencies.frontend.mode="bundled"` 和 `bundle` 字段声明。需要构建的插件可把生成物输出到 `frontend/dist/`，并声明 `mode="build"`、`build` 命令和 `dist` 路径；`dist` 应视为可再生成产物。

### `/api/plugins/{plugin_id}/api/*`

插件自己的后端 API。示例 `cclib` 插件提供：

- `POST /api/plugins/cclib/api/probe`
- `GET /api/plugins/cclib/api/structures/preview`
- `GET /api/plugins/cclib/api/structures/frame`
- `GET /api/plugins/cclib/api/structures/frames`
- `GET /api/plugins/cclib/api/structures/frames.bin`

## 队列状态

### `GET /api/queue/list?current_user_only=false`

返回调度系统队列。Slurm 优先使用 `squeue --json`；不可用时回退到可解析文本。PBS 使用对应 PBS 命令。

### `GET /api/queue/job/{job_id}`

返回作业详情，例如 Slurm 的 `scontrol show job {job_id}` 解析结果。

### `POST /api/queue/action`

对作业执行调度器动作。

```json
{
  "job_id": "123456",
  "action": "cancel"
}
```

常见动作包括 `cancel`、`hold`、`release`。具体支持取决于后端 provider。

前端封装：`frontend/src/api/queue.ts`。

## 作业提交

### `POST /api/jobs/submit`

在指定工作目录执行 `sbatch <script>` 或 `qsub <script>`。

```json
{
  "workdir": "/workspace/project/co2rr_opt",
  "script": "run.sh",
  "scheduler": "slurm",
  "command": "sbatch"
}
```

安全约束：

- `workdir` 必须在 `workspace.root` 内。
- `script` 必须是文件名，不能是路径。
- `script` 只允许字母、数字、点、下划线和短横线。
- 后端不会执行任意 shell 字符串。

前端封装：`frontend/src/api/jobs.ts`。

## 终端

终端后端接口见 `frontend/src/api/terminal.ts` 和 `backend/app/api/terminal.py`。前端组件为 `frontend/src/components/terminal/TerminalPanel.vue`。

常用交互：

- 创建终端会带上当前文件管理器目录作为 `cwd`。
- 文件管理器与终端支持目录同步：`follow` 表示终端跟随文件管理器，`bidirectional` 表示终端 cwd 变化也会反向打开文件管理器目录。
- 终端接收文件拖放时，会向当前活跃 tab 写入输入数据。当前约定是路径串前置一个空格，多个绝对路径用空格连接，例如 ` /abs/a /abs/b`。

如果新增终端相关模块，优先通过已有 websocket 消息发送：

```json
{
  "type": "input",
  "data": " ls\n"
}
```

## 前端窗口交互协议

### 文件拖拽 payload

文件管理器长按文件行后进入“文件拖拽”模式；普通按住拖动仍用于多选。拖拽实现集中在：

- 写入端：`frontend/src/components/FileTree.vue`
- 协议工具：`frontend/src/api/fileDrag.ts`
- 终端接收端：`frontend/src/components/terminal/TerminalPanel.vue`
- 预览接收端：`frontend/src/views/Workspace.vue`

拖拽时会写入以下 `DataTransfer` 类型：

| 类型 | 内容 | 用途 |
| --- | --- | --- |
| `application/x-chemweb-files` | JSON payload | chemweb 内部窗口优先读取 |
| `application/x-chemweb-file-paths` | JSON string array | 轻量路径列表备用 |
| `text/plain` | ` /abs/a /abs/b` | 拖到终端或其他文本输入 |
| `text/uri-list` | 下载 URL | 拖到浏览器外部触发下载 |
| `DownloadURL` | Chrome 下载拖拽格式 | 外部下载兼容增强 |

JSON payload：

```json
{
  "source": "chemweb:file-manager",
  "version": 1,
  "paths": ["/workspace/project/a.xyz"],
  "items": [
    {
      "name": "a.xyz",
      "path": "/workspace/project/a.xyz",
      "type": "file",
      "size": 128,
      "mtime": "2026-05-25T10:00:00",
      "extension": ".xyz",
      "preview_type": "structure",
      "format": "xyz"
    }
  ]
}
```

新增窗口如果要接收文件拖拽，推荐这样写：

```ts
import { hasChemwebFileDrag, readChemwebFileDrag } from '../api/fileDrag'

function handleDragOver(event: DragEvent) {
  if (!hasChemwebFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleDrop(event: DragEvent) {
  const payload = readChemwebFileDrag(event.dataTransfer)
  if (!payload) return
  event.preventDefault()
  // payload.paths 是绝对路径列表；payload.items 带文件类型与预览类型。
}
```

### 推荐的窗口行为

- 文件管理器 -> 浏览器外部：打开 `text/uri-list` 中的下载 URL。单文件直接下载，多文件或目录下载 zip。
- 文件管理器 -> 终端：向当前 tab 输入 ` ${paths.join(' ')}`，不自动回车。
- 文件管理器 -> 预览：只打开第一个路径，并切换到预览面板。
- 文件管理器 -> 插件结构 provider：如果插件 UI 已加载并注册 active preview provider，文件管理器可先调用插件 `probe`，匹配成功后把插件 `StructureSource` 和文件路径发送到现有预览窗口。
- 文件管理器图标：已加载插件注册 active preview provider 后，文件列表会用 `accepts.extensions`、`accepts.filenames`、`accepts.preview_types` 做轻量匹配；匹配到的文件显示与结构文件一致的小眼睛图标。列表渲染阶段不调用 `probe`，真实可预览性仍在双击打开时确认。
- 文件管理器 -> 新模块：默认读取 `application/x-chemweb-files`。如果模块只需要路径，使用 `payload.paths`；如果需要判断结构/文本/目录，使用 `payload.items[*].preview_type` 和 `type`。
- 外部文件 -> 工作区：根 `Workspace.vue` 只在 `DataTransfer.types` 包含 `Files` 时触发上传，避免和内部文件拖拽冲突。

### 给新增模块的实现提示

- 不要解析 DOM 文本来拿路径；始终读取拖拽 payload 或调用文件 API。
- 组件需要“打开文件”时，优先接受绝对路径字符串，再由父级决定调用 `readFile`、`readAsePreview` 或目录打开。
- 插件预览 provider 的类型与轻量匹配工具在 `frontend/src/api/filePreviewProviders.ts`；文件列表组件通过 `previewProviders` 属性接收当前 active providers。
- 需要下载时优先使用 `downloadUrl(path)` 或 `downloadSelectionUrl(paths)`，不要硬编码接口地址。
- 需要预览结构时，先看 `preview_type === 'structure'`，同时兼容 VASP 强制文件名。
- 大文件预览必须走确认流程，确认后才使用 `force=true`。
- 所有路径展示可以是绝对路径；所有后端请求仍会做工作区越界校验。
