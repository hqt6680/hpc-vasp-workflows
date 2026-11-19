# PBS 作业回传

安装和站点配置见 `vasp-pbs` 技能目录下的 `references/setup.md`。将本目录复制到目标项目的 `scripts/` 后，在项目根目录执行命令。

```powershell
python scripts/pbs_watch.py add 1234.cluster scf Materials/example
.\scripts\install_pbs_watch.ps1 -Action Start
python scripts/pbs_watch.py status
```

命令使用实际作业 ID、作业名和相对算例路径。若终端没有当前 Codex 聊天 UUID，在 `add` 命令末尾加 `--thread <chat-uuid>`。

- 每两分钟批量查询已登记的作业。SSH 不可用时逐步延长查询间隔，最大为 15 分钟。无待处理作业或事件时自动退出。
- 通过现有 Windows Codex Desktop 的本机 IPC 回传。活动聊天收到 `steered`，空闲且仍由 Desktop 接管的聊天收到 `started`。监听器没有 Codex 排队、启动程序或打开窗口的入口。
- 收到回传后通过 SSH 核验 PBS 和科学输出。处理完用 `python scripts/pbs_watch.py ack <event_id>` 确认。
- `pending` 表示本机待投递。若为 `sending`，先核对原聊天是否收到，确认未收到才运行 `python scripts/pbs_watch.py retry <event_id>` 并启动监听。
