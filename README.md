# chemweb

`chemweb` 是一个面向计算催化、计算化学和材料模拟目录的轻量级 Web 工作台 MVP。它适合部署在远程 Linux 服务器或 HPC 登录节点上，通过 SSH 端口转发在本地浏览器访问。

当前版本提供文件管理、文本/日志预览、自定义三维结构预览、Slurm 队列查看、`sbatch` 作业提交和 `scancel` 作业取消。

## 技术栈

- 后端：Python 3.10+、FastAPI、Uvicorn、Pydantic
- 前端：Vue 3、Vite、Element Plus、自定义 Canvas 结构显示器
- 调度系统：MVP 优先支持 Slurm

## 安装

建议在项目根目录 `D:\Git\chemweb` 或远程服务器上的项目根目录创建虚拟环境。

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"

npm.cmd --prefix frontend install
npm.cmd --prefix frontend run build
```

Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

npm --prefix frontend install
npm --prefix frontend run build
```

安装完成后，命令行入口为：

```bash
chemweb --help
```

## 配置

复制并修改 `config.yaml`。最重要的是设置工作区根目录：

```yaml
workspace:
  root: /home/user
```

所有文件读写、上传、下载、删除、重命名和作业提交都会被限制在 `workspace.root` 之内，防止访问 `/etc/passwd`、`/root` 或其他用户目录。

## 启动

```bash
chemweb --config config.yaml --host 127.0.0.1 --port 8888
```

开发模式可以分别启动后端和前端：

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8888 --reload
npm.cmd --prefix frontend run dev
```

如果在 Linux 或 macOS 上开发，把 `npm.cmd` 换成 `npm`。

## SSH 端口转发

在远程服务器上启动：

```bash
chemweb --config config.yaml --host 127.0.0.1 --port 8888
```

在本地机器执行端口转发：

```bash
ssh -p 22 -L 8888:127.0.0.XX:8888 user@server
# 等价于 -L 127.0.0.1:8888:127.0.0.XX:8888 所以远程.XX 本地还是.1
# 127.0.0.1等价localhost
```

然后在本地浏览器打开：

```text
http://localhost:8888
```

## MVP 功能

- 浏览 `workspace.root` 及其子目录
- 上传、下载、删除、重命名文件，新建目录
- 读取和保存文本文件
- 预览 `.txt`、`.log`、`.out`、`.in`、`.inp` 等文本文件
- 预览 `.xyz`、`.pdb`、`.mol`、`.sdf`、`.cif` 结构文件
- 在浏览器中切换结构显示模式：stick、sphere、line
- 查看 Slurm 队列，支持手动刷新和自动刷新
- 查看 Slurm 作业详情，取消作业
- 在当前目录提交 `sbatch run.sh`
- 读取日志文件末尾 N 行，支持手动刷新和自动刷新

## Slurm 说明

后端只调用固定白名单命令：

- `squeue`
- `scontrol show job <job_id>`
- `scancel <job_id>`
- `sbatch <script>`

作业提交接口只接受脚本文件名，例如 `run.sh`。它不会执行任意 shell 命令，也不会接受包含路径或 shell 控制字符的脚本参数。

## 安全注意事项

- 默认绑定 `127.0.0.1`，建议通过 SSH 隧道访问。
- 将 `workspace.root` 设置为尽可能小的工作目录。
- 普通文件读取受 `workspace.max_read_size_mb` 限制，大文件请使用日志 tail 或下载。
- 如需禁止删除操作，可设置 `workspace.allow_delete: false`。

## API 文档

接口说明见 [docs/API.md](docs/API.md)。

启动服务后也可以访问 FastAPI 自动文档：

```text
http://127.0.0.1:8888/docs
```

## 测试

```bash
python -m pytest
```

当前最小测试覆盖路径安全、文件类型识别、文件 API 读写和基础应用启动。
