# chemssh API 与窗口交互指南

本文档面向后续维护者和 coding agent。目标是让新模块可以快速接入 chemssh 的后端接口、文件管理器、终端、预览器和队列窗口。

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

返回当前服务的轻量身份信息。`chemssh` CLI 启动前会用此接口判断目标端口是否已由可复用的 ChemSSH 服务占用。

```json
{
  "app": "chemssh",
  "project_version": "0.2.0",
  "pid": 12345,
  "scheduler": "slurm",
  "workspace_root": "/home/user"
}
```

启动复用规则：

- 端口未占用：正常启动新服务。
- 端口占用且 `/api/system/identity` 返回 `app="chemssh"`：默认仅当 `workspace_root` 与当前配置一致时复用已有服务。
- 端口占用但不是 ChemSSH，或无法读取身份信息：启动失败并报告端口占用。

CLI 参数：

- `--reuse-existing auto`：默认值，复用同工作区的已有 ChemSSH 服务。
- `--reuse-existing never`：不复用已有服务；端口已占用时直接失败。
- `--reuse-existing any-chemssh`：复用该端口上的任意 ChemSSH 服务，即使工作区不同。
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
- `relative_path`: 可选，上传到目标目录下的相对路径。用于文件夹上传，例如 `case/A/input.inp`。后端会逐段校验路径并自动创建父目录，路径仍必须留在工作区内。

前端封装：`uploadFile(path, file, { relativePath, onProgress })`。文件夹上传由 `Workspace.vue` 在上传前检查当前目录顶层重名项，并按用户选择逐文件调用该接口：

- 上传前会先规范化 `relative_path`：路径段中的空白字符自动替换为 `_`，然后按后端规则预检每个路径段是否只含字母、数字、点、下划线和短横线。不合规项目会在开始传输前跳过并提示，不等待后端上传失败。
- `overwrite`：同名文件写入覆盖；同名目录只合并目录树，内部仅覆盖实际上传且同名的文件，远程额外文件保留。
- `skip`：跳过该顶层冲突项。
- `suffix`：把冲突顶层文件或文件夹自动改名为 `.new` 后缀，例如 `A` -> `A.new`。
- `cancel`：取消本批上传。

### `GET /api/files/download?path=/workspace/project/result.out`

下载单个文件。路径必须指向文件，目录会返回 `NOT_A_FILE`。

### `POST /api/files/download-archive`

将多个文件或目录打包为 `chemssh-selection.zip`。工具栏“下载”使用此接口。

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

### `POST /api/files/move`

把一个或多个文件/目录移动到目标目录。后端会先校验所有路径仍在工作区内、目标必须是已存在目录、不能移动工作区根目录、不能把目录移动到自身或子目录内。默认 `paths` 模式下目标目录已有同名项会返回 `PATH_EXISTS`；前端拖拽移动会先检查目标目录，同名时弹出和上传一致的冲突处理：覆盖、跳过、添加 `.new` 后缀或取消。

兼容的简单请求：

```json
{
  "paths": [
    "/workspace/project/a.xyz",
    "/workspace/project/case_dir"
  ],
  "target_directory": "/workspace/project/done"
}
```

需要表达冲突处理时使用 `items`。`target_name` 省略时使用源文件名；`overwrite=true` 允许覆盖同名文件，或把同名目录递归合并，源目录中同名文件覆盖目标文件，目标目录里额外文件保留。后缀模式由前端生成唯一 `target_name`，例如 `a.xyz.new`。

```json
{
  "target_directory": "/workspace/project/done",
  "items": [
    {
      "path": "/workspace/project/a.xyz",
      "overwrite": true
    },
    {
      "path": "/workspace/project/case_dir",
      "target_name": "case_dir.new"
    }
  ]
}
```

响应：

```json
{
  "success": true,
  "path": "/workspace/project/done",
  "message": "Paths moved"
}
```

失败响应沿用统一的 `{ "error": { "code": "...", "message": "..." } }` 格式。移动接口的 `message` 会给出中文详细原因，常见错误码包括 `PATH_NOT_FOUND`（源路径不存在）、`DIRECTORY_NOT_FOUND`（目标文件夹不存在）、`PATH_EXISTS`（目标已有同名项目）、`MOVE_INTO_SELF`（移动到自身或子目录）、`MOVE_TYPE_CONFLICT`（文件和文件夹类型冲突）和 `MOVE_FAILED`（底层 `mv` 或文件系统移动失败）。前端文件管理器会优先展示后端返回的中文详情；如果只拿到旧版英文或错误码，则兜底转换为中文提示。

### `POST /api/files/copy`

把一个或多个文件/目录复制到目标目录。请求体和 `POST /api/files/move` 保持一致，支持 `paths` 简单模式和 `items` 冲突处理模式。复制目录时如果 `overwrite=true` 且目标已有同名目录，后端会递归合并目录树：源目录中的同名文件覆盖目标文件，目标目录里的额外文件保留。复制不会删除源项目。

```json
{
  "target_directory": "/workspace/project/done",
  "items": [
    {
      "path": "/workspace/project/a.xyz",
      "overwrite": true
    },
    {
      "path": "/workspace/project/case_dir",
      "target_name": "case_dir.new"
    }
  ]
}
```

响应：

```json
{
  "success": true,
  "path": "/workspace/project/done",
  "message": "Paths copied"
}
```

常见错误码包括 `PATH_NOT_FOUND`、`DIRECTORY_NOT_FOUND`、`PATH_EXISTS`、`COPY_INTO_SELF`、`COPY_SAME_PATH`、`COPY_TYPE_CONFLICT`、`COPY_WORKSPACE_ROOT` 和 `COPY_FAILED`。前端封装：`copyPaths(paths, targetDirectory, entries)`，定义在 `frontend/src/api/files.ts`。

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

支持格式由 `backend/app/services/file_types.py` 与 ASE 能力共同决定。当前常见格式包括 `xyz`、`extxyz`、`traj`、`pdb`、`mol`、`sdf`、`cif`、`xsd`、`db`，并强制识别 `POSCAR`、`CONTCAR`、`XDATCAR`、`OUTCAR` 等 VASP 文件名。

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

`frames.bin` 继续使用 `application/vnd.chemssh.structure+bin`，由现有 Brotli middleware 自动压缩。

## 插件

插件目录默认扫描项目根目录下的 `plugins/`。扫描阶段只读取 `chemssh-plugin.json`，不会导入插件后端或加载插件 UI。用户从工作区右侧功能区的 `+` 菜单打开插件面板后，前端才调用激活接口。

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
    "python": "D:/Git/chemssh/.venv/Scripts/python.exe",
    "requirements": "D:/Git/chemssh/plugins/cclib/backend/requirements.txt",
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

`host` 会修改运行 chemssh 的当前 Python 环境；`venv` 会创建或复用插件目录内的虚拟环境。安装结果会写入插件状态文件，不改写插件清单。

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

终端会话按浏览器 client id 轻量隔离。前端通过 `frontend/src/api/clientSession.ts` 在 `localStorage` 中保存 `chemssh.clientId.v1`，并在终端 HTTP 请求中发送：

```http
X-ChemSSH-Client-Id: client_xxx
```

WebSocket 连接使用 query 参数：

```text
/api/terminal/ws/{session_id}?client_id=client_xxx
```

后端只会列出、关闭、连接当前 client id 拥有的终端会话。`terminal.max_sessions` 是每个 client id 的上限，不是全局上限。client id 只用于会话隔离，不代表用户身份或安全认证。

### `POST /api/terminal/sessions`

创建终端会话。请求必须带 `X-ChemSSH-Client-Id`，用于把会话归属到当前浏览器客户端。

```json
{
  "cwd": "/workspace/project",
  "shell": null,
  "rows": 30,
  "cols": 120,
  "vim_compatibility": true
}
```

字段说明：

- `cwd`：可选，终端启动目录；省略时使用工作区根目录。后端会通过 `WorkspaceSecurity` 校验路径必须留在工作区内。
- `shell`：可选，指定 shell；省略时使用后端默认 shell。
- `rows` / `cols`：可选，初始终端尺寸；`rows` 范围为 `2..200`，`cols` 范围为 `20..500`。
- `vim_compatibility`：可选，默认 `true`。只影响新建会话是否创建 `vi` / `vim` 兼容 shim，不影响已有终端。

响应：

```json
{
  "session_id": "term_xxx",
  "cwd": "/workspace/project",
  "shell": "/bin/bash",
  "created_at": "2026-06-05T12:00:00Z",
  "last_active_at": "2026-06-05T12:00:00Z",
  "alive": true,
  "clients": 1
}
```

前端封装：`createTerminalSession(payload)`，类型定义在 `frontend/src/api/terminal.ts`。

### `GET /api/terminal/sessions`

列出当前 `X-ChemSSH-Client-Id` 拥有的终端会话。响应形如：

```json
{
  "items": [
    {
      "session_id": "term_xxx",
      "cwd": "/workspace/project",
      "shell": "/bin/bash",
      "created_at": "2026-06-05T12:00:00Z",
      "last_active_at": "2026-06-05T12:05:00Z",
      "alive": true,
      "clients": 1
    }
  ]
}
```

### `DELETE /api/terminal/sessions/{session_id}`

关闭当前 `X-ChemSSH-Client-Id` 拥有的指定终端会话。

```json
{
  "success": true
}
```

常用交互：

- 创建终端会带上当前文件管理器目录作为 `cwd`。
- 创建终端可传 `vim_compatibility` 布尔值，默认 `true`。前端终端设置中的“Vim 兼容模式”会保存到 `localStorage` 并随新建会话发送；关闭后只影响之后新建的终端会话。
- 文件管理器与终端支持目录同步：`follow` 表示终端跟随文件管理器，`bidirectional` 表示终端 cwd 变化也会反向打开文件管理器目录。
- 终端接收文件拖放时，会向当前活跃 tab 写入输入数据。当前约定是路径串前置一个空格，多个绝对路径用空格连接，例如 ` /abs/a /abs/b`。
- 终端支持“中键粘贴当前终端选区文本”。该行为依赖宿主环境放行中键事件；常规浏览器通常会拦截为自动滚屏，自定义 WebView2 启动器可通过关闭默认中键滚轮后启用。

如果新增终端相关模块，优先通过已有 websocket 消息发送：

```json
{
  "type": "input",
  "data": " ls\n"
}
```

### 终端 `rz` / `sz` 接管

终端会话启动时，后端会创建临时 `rz`、`sz` shim，并把 shim 目录放到该终端进程的 `PATH` 最前面。脚本或用户命令通过普通 `PATH` 查找调用 `rz` / `sz` 时，不会进入原生 ZMODEM 传输；shim 会向 pty 输出 ChemSSH 私有 OSC 标记，后端读取终端输出时吞掉该标记并转成 WebSocket 传输请求。shim 会阻塞等待前端回传 `transfer_result`，收到成功后以 `0` 退出，收到失败或取消后以非零码退出；这让脚本中位于 `sz` 后面的 `rm` 等清理命令在浏览器下载请求完成后才继续执行。

后端发送上传请求：

```json
{
  "type": "transfer_request",
  "transfer_id": "transfer_xxx",
  "direction": "upload",
  "cwd": "/workspace/project",
  "argv": ["rz", "-y"]
}
```

前端收到 `direction="upload"` 后打开浏览器文件选择器，并走与文件管理器相同的上传准备流程上传到该终端当前目录：空白字符会先改为 `_`，路径段预检失败的文件不会开始传输。

后端发送下载请求：

```json
{
  "type": "transfer_request",
  "transfer_id": "transfer_xxx",
  "direction": "download",
  "cwd": "/workspace/project",
  "argv": ["sz", "result.out"],
  "paths": ["/workspace/project/result.out"]
}
```

前端收到 `direction="download"` 后，单文件使用 `downloadUrl(path)`，多文件或目录使用 `downloadSelectionUrl(paths, { forceArchive: true })`。

前端完成、失败或取消后回传结果：

```json
{
  "type": "transfer_result",
  "transfer_id": "transfer_xxx",
  "success": true,
  "message": "Uploaded 1 file(s)"
}
```

后端收到 `transfer_result` 后，会写入 shim 专属临时 ack 文件释放正在等待的 `rz` / `sz` 进程。ack 路径只允许位于该终端会话创建的临时 shim 目录内，不能由前端任意指定。

安全规则：

- shim 只影响当前终端会话子进程的 `PATH`，不会修改系统环境。
- `rz` 上传目标目录来自终端 shim 上报的 cwd，后端会按 workspace 安全规则解析。
- `sz` 参数由后端解析为 workspace 内路径；越界、缺失或不存在的路径会以 `transfer_request.error` 返回，前端显示失败并回传 `transfer_result`。
- 如果脚本显式调用 `/usr/bin/rz`、`/usr/bin/sz` 等绝对路径，会绕过 shim。后端会在 pty 输出流中识别常见原生 ZMODEM 起始特征并发送 `Ctrl+C` 中断，避免终端继续卡死。原生 `rz` 可继续接管为浏览器上传；原生 `sz` 在协议流中通常无法可靠恢复原始文件参数，因此会提示改用 PATH 解析到的 `sz` shim，除非后续实现完整 ZMODEM 接收器。

### 终端 `vi` / `vim` 兼容 shim

终端会话支持“Vim 兼容模式”，默认开启。开启后，临时 shim 目录还会放置 `vi` 和 `vim` 包装脚本。Linux Vim 在 xterm 兼容终端中会发起 `t_RV`、`t_u7`、`t_RF`、`t_RB`、`t_RK` 等终端探测；当前 WebTerminal 链路对这些探测的完整响应仍不够稳定，会导致 Vim 启动后等待终端响应，看起来像卡死。包装脚本只在真实命令是 Vim 时注入：

```bash
--cmd 'set t_RV= t_u7= t_RF= t_RB= t_RK='
```

前端设置面板可以手动关闭“Vim 兼容模式”，关闭后创建会话请求会发送 `vim_compatibility: false`，后端仍创建 `rz` / `sz` shim，但不会创建 `vi` / `vim` 包装脚本。脚本会先从移除 shim 目录后的 `PATH` 中找到真实 `vi` / `vim`。如果真实命令不是 Vim，则原样执行；如果用户显式调用 `/usr/bin/vim` 等绝对路径，也会绕过 shim。该兼容层只影响 ChemSSH 创建的终端会话，不修改用户的 `~/.vimrc` 或系统配置。后续如果前端完整实现 Vim 所需的 xterm 查询响应，可移除此 shim。

## 客户端缓存

客户端缓存用于保存同一个浏览器 `client_id` 的 UI 状态，例如画板布局、窗口大小、tail 行数等。它不是认证或权限系统，不应保存密码、token 等敏感信息。

前端封装：

```text
frontend/src/api/clientCache.ts
```

后端实现：

```text
backend/app/api/client_cache.py
backend/app/services/client_cache_service.py
```

默认保存位置：

```text
cache/<client_id>/
```

目录内文件：

- `meta.json`：`created_at`、`last_seen_at`、`last_saved_at`。
- `preferences.json`：用户偏好，例如 tail 行数。
- `boards.json`：画板、viewport、窗口布局和窗口 payload。

后端启动时会清理超过 `client_cache.cleanup_offline_days` 没有上线的 client cache，默认 14 天。

### `GET /api/client-cache`

读取当前客户端缓存。请求必须带：

```http
X-ChemSSH-Client-Id: client_xxx
```

响应：

```json
{
  "enabled": true,
  "client_id": "client_xxx",
  "preferences": {
    "version": 1,
    "logs": {
      "tailLines": 20
    }
  },
  "boards": {
    "version": 1,
    "activeBoardId": "board_xxx",
    "boards": []
  },
  "updated_at": "2026-06-05T12:00:00Z"
}
```

### `PUT /api/client-cache/preferences`

保存用户偏好。

```json
{
  "version": 1,
  "logs": {
    "tailLines": 80
  },
  "workspace": {
    "fileTreeWidth": 360,
    "sidePaneWidth": 420,
    "queueHeight": 260,
    "currentPath": "/workspace/project",
    "showHiddenFiles": false,
    "activeWorkPanelId": "builtin:preview"
  },
  "canvas": {
    "lastBoardId": "board_xxx"
  }
}
```

前端通过 `frontend/src/api/clientPreferences.ts` 合并保存偏好，避免画板、工作台和日志窗口分别保存时互相覆盖。当前接入项包括：

- `workspace.fileTreeWidth`：工作台左侧文件管理器宽度。
- `workspace.sidePaneWidth`：工作台右侧窗口宽度。
- `workspace.queueHeight`：工作台右侧队列/日志高度。
- `workspace.currentPath`：工作台当前目录。
- `workspace.showHiddenFiles`：是否显示隐藏文件。
- `workspace.activeWorkPanelId`：工作台右侧活跃面板。
- `logs.tailLines`：tail 行数。

### `PUT /api/client-cache/boards`

保存画板布局。

```json
{
  "version": 1,
  "activeBoardId": "board_xxx",
  "boards": [
    {
      "id": "board_xxx",
      "name": "Board 1",
      "createdAt": "2026-06-05T12:00:00Z",
      "updatedAt": "2026-06-05T12:05:00Z",
      "viewport": {
        "x": 120,
        "y": 80,
        "zoom": 1
      },
      "windows": [
        {
          "id": "window_xxx",
          "type": "tail",
          "title": "slurm.out",
          "x": 80,
          "y": 80,
          "width": 520,
          "height": 340,
          "zIndex": 2,
          "payload": {
            "path": "/workspace/project/slurm.out",
            "lines": 80,
            "boundFileManagerId": "window_files"
          }
        },
        {
          "id": "window_files",
          "type": "file-manager",
          "title": "project",
          "x": 40,
          "y": 60,
          "width": 620,
          "height": 430,
          "zIndex": 1,
          "payload": {
            "path": "/workspace/project",
            "bindingNumber": 1,
            "bindingColor": "#176b87"
          }
        }
      ]
    }
  ]
}
```

画板窗口交互约定：

- 新建窗口菜单顺序为：文件、终端、预览、队列、Tail、插件。空画板的默认新建入口创建文件管理窗口。
- 文件管理窗口会把当前目录保存到 `payload.path`，标题只显示当前目录名；新建时写入 `payload.bindingNumber` 和 `payload.bindingColor`，用于窗口类型标签、绑定徽标和关系线的一致颜色/编号。绑定到该文件管理器的 Tail 窗口在单击选中任意文件时会自动更新 `payload.path`，与工作台 Tail 的选中文件行为保持一致。画板文件管理窗口完成内部移动后会向 `CanvasBoard.vue` 上报受影响目录，画布层按各文件管理器当前目录匹配并递增 `refreshToken`，因此源目录窗口、目标目录窗口，以及其它打开相同目录的窗口都会自动刷新。
- 文件管理器列表顶部在存在上级目录时固定显示 `..` 文件夹行。该行不参与选择、重命名或删除；双击进入上一级，也可作为内部文件拖拽的移动目标。工具栏不再提供“上一级”按钮；原位置改为类似 XFTP 的“后退”按钮和历史下拉，每个文件管理器本地记录最近 20 个用户主动访问过的目录，历史下拉显示完整绝对路径。刷新、上传完成、移动完成等重载当前目录的操作不会写入历史。
- Tail 窗口通过 `payload.boundFileManagerId` 记录绑定的文件管理窗口。画板 Tail 不提供手动路径输入，绑定入口位于 Tail 标题栏右侧的连接图标；日志内容仍由 `LogViewer.vue` 调用 `GET /api/files/tail`。
- Terminal 窗口通过 `payload.tabBindings` 保存当前终端标签页绑定摘要，形如：

```json
[
  {
    "tabId": "terminal_tab_1",
    "title": "project",
    "cwd": "/workspace/project",
    "syncMode": "follow",
    "boundFileManagerId": "window_files",
    "active": true
  }
]
```

终端标签页绑定到文件管理窗口后，默认进入跟随目录模式；切到双向同步时，终端 `cwd` 变化会回写对应的文件管理窗口，而不是全局工作台文件管理器。画板会用窗口标题徽标和关系线展示文件管理器、Tail、Terminal 标签页之间的绑定关系。Terminal 的大窗口按钮会把整个 TerminalPanel teleport 到 `body` 后全视口覆盖，避免被画板 transform 限制；多标签页切换、拖拽排序和标签级绑定保持不变。

### `POST /api/client-cache/heartbeat`

刷新当前 `client_id` 的 `last_seen_at`。前端启动时调用一次，之后每 5 到 10 分钟调用一次。

### `DELETE /api/client-cache`

清理当前请求头 `X-ChemSSH-Client-Id` 对应的缓存目录。该接口不接受前端传入路径，只删除服务端解析出的 `cache/<client_id>/`。

设置页“清理当前缓存”会调用该接口，同时清理前端本地兜底缓存，然后刷新页面，让工作台布局、tail 行数、画板列表和窗口布局回到默认值。

响应：

```json
{
  "success": true,
  "client_id": "client_xxx",
  "removed": true
}
```

## 前端窗口交互协议

### 无边画板

顶部“画板”视图由 `frontend/src/views/CanvasBoard.vue` 实现，窗口外壳由 `frontend/src/components/canvas/CanvasWindow.vue` 统一管理。画板状态保存在 client cache 的 `boards.json` 中。

第一版画板窗口类型：

| 类型 | 当前行为 |
| --- | --- |
| `file-manager` | 渲染画板文件管理器窗口，可浏览目录并把文件拖给其它窗口 |
| `queue` | 渲染 `QueueStatus.vue`，队列仍可打开作业工作目录 |
| `tail` | 渲染 `LogViewer.vue`，保存路径和 tail 行数 |
| `terminal` | 渲染 `TerminalPanel.vue`，窗口 resize 后触发 terminal fit |
| `preview` | 渲染画板预览窗口，复用 `FilePreview.vue`、文本读取/保存和 ASE 结构预览接口 |
| `plugin` | 渲染插件 iframe 窗口，可选择插件 panel，激活后发送 `chemssh:plugin:init` |

窗口布局使用画布坐标，而不是屏幕像素。保存字段包括：

- `x`、`y`：画布坐标。
- `width`、`height`：窗口尺寸。
- `zIndex`：窗口层级。
- `payload`：窗口类型自己的轻量状态，例如 tail 的 `{ path, lines }`。

`file-manager` 窗口的 `payload.path` 保存当前目录。画板文件管理器复用工作台的完整工具栏能力：刷新、上级目录、新建文件、新建文件夹、显示隐藏文件、上传文件/文件夹、下载、重命名和删除。外部文件拖拽上传只在具体文件管理器窗口内响应，目标目录就是该窗口当前目录，便于多个文件管理器并存时选择上传位置。双击目录进入目录；双击文件统一打开 `preview` 窗口。Tail 窗口不由双击文件触发，而是和工作台一样由当前文件选择驱动：绑定文件管理器后，单击/选中文件会更新对应 Tail 路径。

`preview` 窗口的 `payload.path` 保存当前文件。从文件管理器打开或从内部文件拖拽打开时还会保存 `payload.previewType` 与 `payload.format`，预览窗口优先使用后端文件类型判定结果，再按文件名和扩展名兜底判断结构文件；大文件沿用现有确认流程。预览大窗口与 Terminal 大窗口一致，使用 `Teleport to="body"` 加 `position: fixed; inset: 0` 覆盖整个页面，不使用 Element Plus fullscreen dialog。

`plugin` 窗口保存 `pluginId`、`panelId`、`assetUrl`、`apiBase` 和标题。iframe 加载后接收：

```json
{
  "type": "chemssh:plugin:init",
  "version": 1,
  "pluginId": "plugin_id",
  "panelId": "panel_id",
  "instanceId": "window_xxx",
  "locale": "zh",
  "theme": "light",
  "apiBase": "/api/plugins/plugin_id/api",
  "assetBase": "/api/plugins/plugin_id/assets",
  "initialFile": null
}
```

画板 UI 要保持工具化和低干扰：浅色点阵背景、贴边工具栏、图标按钮加 tooltip、窗口薄边框和不超过 8px 的圆角。多窗口、窄屏和不同缩放比例下不得出现文字溢出或控件重叠。

### 文件拖拽 payload

文件管理器长按文件行后进入“文件拖拽”模式；普通按住拖动仍用于多选。拖拽实现集中在：

- 写入端：`frontend/src/components/FileTree.vue`
- 协议工具：`frontend/src/api/fileDrag.ts`
- 终端接收端：`frontend/src/components/terminal/TerminalPanel.vue`
- 预览接收端：`frontend/src/views/Workspace.vue`

拖拽时会写入以下 `DataTransfer` 类型：

| 类型 | 内容 | 用途 |
| --- | --- | --- |
| `application/x-chemssh-files` | JSON payload | chemssh 内部窗口优先读取 |
| `application/x-chemssh-file-paths` | JSON string array | 轻量路径列表备用 |
| `text/plain` | ` /abs/a /abs/b` | 拖到终端或其他文本输入 |
| `text/uri-list` | 下载 URL | 拖到浏览器外部触发下载 |
| `DownloadURL` | Chrome 下载拖拽格式 | 外部下载兼容增强 |

写入端设置 `effectAllowed="copyMove"`：拖到终端、预览或浏览器外部仍按原来的 copy/download 行为处理；拖回文件管理器目录行时，只有合法目标文件夹会 `preventDefault()` 并设置 `dropEffect="move"`，其它行和空白区域保持浏览器默认禁止图标。

JSON payload：

```json
{
  "source": "chemssh:file-manager",
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
import { hasChemSSHFileDrag, readChemSSHFileDrag } from '../api/fileDrag'

function handleDragOver(event: DragEvent) {
  if (!hasChemSSHFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleDrop(event: DragEvent) {
  const payload = readChemSSHFileDrag(event.dataTransfer)
  if (!payload) return
  event.preventDefault()
  // payload.paths 是绝对路径列表；payload.items 带文件类型与预览类型。
}
```

### 推荐的窗口行为

- 文件管理器 -> 浏览器外部：打开 `text/uri-list` 中的下载 URL。单文件直接下载，多文件或目录下载 zip。
- 文件管理器 -> 浏览器外部拖拽目录时，即使只拖了一个目录，也使用 `download-selection` 返回 zip。
- 文件管理器 -> 当前目录另一个文件夹：长按文件行进入内部文件拖拽后，可拖动当前选择的多个文件/文件夹到目录行。合法目标目录会高亮并以 move 光标提示；松开后先读取目标目录，若有同名项则使用和上传一致的冲突弹窗选择覆盖、跳过、添加 `.new` 后缀或取消，然后调用 `movePaths(paths, targetDirectory, entries)`，也就是 `POST /api/files/move`。文件行、空白区域、选中的目标目录、自身/子目录等非法位置不接收目录行移动 drop，保留默认禁止图标。画板文件管理窗口在内部拖拽期间还会显示当前目录悬浮投放区：一个用于移动到该窗口当前目录，另一个用于复制到该窗口当前目录。复制区使用 `copyPaths(paths, targetDirectory, entries)`，也就是 `POST /api/files/copy`；同名冲突仍使用覆盖、跳过、添加 `.new` 后缀或取消。拖到画板文件管理窗口的非目录行或空白区域时，会按移动到该窗口当前目录处理，类似 SFTP pane 级 drop 行为；目录行仍作为更精确的移动目标优先处理，复制只通过复制悬浮区触发。外部文件拖入画板文件管理窗口时显示留有少量边距的窗口级圆角“松开以上传文件”遮罩，目标目录就是该窗口当前目录，不支持直接拖拽上传到列表中的子文件夹。
- 文件管理器 -> 终端：向当前 tab 输入 ` ${paths.join(' ')}`，不自动回车。
- 文件管理器 -> 预览：只打开第一个路径，并切换到预览面板。
- 预览面板统一使用结构/文本切换窗口；结构与文本子视图保活，文件管理器切换目录不会清空当前预览目标，打开普通文件时进入文本视图，只有当前目标可作为结构预览时才显示结构切换入口。结构加载和重绘期间会在旧结构上显示非阻塞半透明遮罩；继续打开下一个结构会取消上一条结构 preview 请求，并且旧响应不能覆盖新状态。预览器工具栏提供“大窗口打开”按钮，使用与 Terminal 一致的 `Teleport to="body"` 固定全页层复用当前结构或文本预览器，适合临时放大查看而不改变当前文件选择。
- 文件管理器 -> 插件结构 provider：如果插件 UI 已加载并注册 active preview provider，文件管理器可先调用插件 `probe`，匹配成功后把插件 `StructureSource` 和文件路径发送到现有预览窗口。
- 文件管理器图标：已加载插件注册 active preview provider 后，文件列表会用 `accepts.extensions`、`accepts.filenames`、`accepts.preview_types` 做轻量匹配；匹配到的文件显示与结构文件一致的小眼睛图标。列表渲染阶段不调用 `probe`，真实可预览性仍在双击打开时确认。
- 文件管理器 -> 新模块：默认读取 `application/x-chemssh-files`。如果模块只需要路径，使用 `payload.paths`；如果需要判断结构/文本/目录，使用 `payload.items[*].preview_type` 和 `type`。
- 文件管理器右键菜单：第一项复制当前选择的第一个绝对路径到剪贴板；右键未选中项时先选中该项再复制。
- 外部文件 -> 工作区：根 `Workspace.vue` 只在 `DataTransfer.types` 包含 `Files` 时触发上传，避免和内部文件拖拽冲突。

### 给新增模块的实现提示

- 不要解析 DOM 文本来拿路径；始终读取拖拽 payload 或调用文件 API。
- 组件需要“打开文件”时，优先接受绝对路径字符串，再由父级决定调用 `readFile`、`readAsePreview` 或目录打开。
- 插件预览 provider 的类型与轻量匹配工具在 `frontend/src/api/filePreviewProviders.ts`；文件列表组件通过 `previewProviders` 属性接收当前 active providers。
- 需要下载时优先使用 `downloadUrl(path)` 或 `downloadSelectionUrl(paths)`，不要硬编码接口地址。
- 需要预览结构时，先看 `preview_type === 'structure'`，同时兼容 VASP 强制文件名。
- 大文件预览必须走确认流程，确认后才使用 `force=true`。
- 所有路径展示可以是绝对路径；所有后端请求仍会做工作区越界校验。
