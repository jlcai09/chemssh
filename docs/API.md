# chemweb API

所有接口都以 `/api` 开头。接口错误统一返回：

```json
{
  "success": false,
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "File not found"
  }
}
```

## 系统信息

### `GET /api/system/info`

返回当前用户、主机名、Python 版本、调度器类型和工作区根目录。

示例响应：

```json
{
  "username": "user",
  "hostname": "node01",
  "cwd": "/home/user/project",
  "python_version": "3.12.7",
  "scheduler": "slurm",
  "workspace_root": "/home/user"
}
```

## 文件管理

### `GET /api/files/list?path=/workspace/project`

列出目录内容。如果省略 `path`，默认列出 `workspace.root`。

### `GET /api/files/read?path=/workspace/project/mol.xyz`

读取较小的文本文件或结构文件。默认读取上限由 `workspace.max_read_size_mb` 控制。
确认要尝试加载大文件时可追加 `force=true` 跳过该预览大小限制。

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

- `path`：目标目录
- `file`：上传文件

### `GET /api/files/download?path=/workspace/project/result.out`

下载单个文件。

### `DELETE /api/files/delete?path=/workspace/project/old.log`

删除文件或目录。只有 `workspace.allow_delete` 为 `true` 时可用。

### `POST /api/files/rename`

重命名文件或目录。

```json
{
  "old_path": "/workspace/project/a.xyz",
  "new_path": "/workspace/project/b.xyz"
}
```

### `GET /api/files/tail?path=/workspace/project/slurm-123.out&lines=300`

读取日志类文件末尾 N 行，适合查看 `.log`、`.out`、`slurm-*.out`、`OUTCAR`、`OSZICAR` 等文件。

## 结构预览

### `GET /api/structures/ase/preview?path=/workspace/project/mol.xyz`

读取结构摘要和初始帧，供自定义结构显示器渲染。
确认要尝试解析大结构文件时可追加 `force=true` 跳过结构预览大小限制；后续帧接口也需要携带相同参数。

### `GET /api/structures/ase/frame?path=/workspace/project/mol.xyz&index=0`

按索引读取单帧结构。支持 `force=true`。

### `GET /api/structures/ase/frames.bin?path=/workspace/project/traj.xyz&start=0&count=64`

读取轨迹二进制帧块。支持 `force=true`。

MVP 支持格式：

- `xyz`
- `pdb`
- `mol`
- `sdf`
- `cif`

## 队列状态

### `GET /api/queue/list`

返回当前用户的调度系统队列。Slurm 会优先尝试 `squeue --json`，不可用时退回到可解析的文本格式。

### `GET /api/queue/job/{job_id}`

返回 `scontrol show job {job_id}` 的键值对详情。

### `POST /api/queue/cancel`

取消作业。

```json
{
  "job_id": "123456"
}
```

后端执行：

```bash
scancel 123456
```

## 作业提交

### `POST /api/jobs/submit`

在指定工作目录执行 `sbatch <script>`。

```json
{
  "workdir": "/workspace/project/co2rr_opt",
  "script": "run.sh",
  "scheduler": "slurm",
  "command": "sbatch"
}
```

`command` is limited to `sbatch` or `qsub`; the backend runs `<command> <script>` in `workdir`.

安全限制：

- `workdir` 必须在 `workspace.root` 之内。
- `script` 必须是文件名，不能是路径。
- `script` 只允许字母、数字、点、下划线和短横线。
- 后端不会执行任意 shell 命令。
