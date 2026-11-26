# VASP PBS 作业回传监听器

本监听器仅追踪显式登记的 zjt PBS 作业。启动后每 120 秒通过 SSH 批量查询同批作业，断线时逐步延长间隔至最长 15 分钟。作业的启动告警、带退出码的 PBS 终态以及已确认的未启动撤回事件，都会自动回传至原 VASP 聊天（同一算例单次查询到的多个事件会合并发送）。所有已登记作业结束且无待发送事件时，监听器自动退出。

## 安装与任务管理

首次使用需具备 Python 和 Node.js 环境，运行以下命令安装本机监听任务：

```powershell
.\scripts\install_pbs_watch.ps1 -Action Install -ResumeAtLogon
```

- 计划任务不设周期触发；`-ResumeAtLogon` 为可选的登录恢复触发，若当前无待处理工作会立即退出，不执行 PBS 查询。
- 常用控制命令：
  - `.\scripts\install_pbs_watch.ps1 -Action Start`：手动启动并恢复待处理作业监听。
  - `.\scripts\install_pbs_watch.ps1 -Action Status`：查看监听器当前状态。
  - `.\scripts\install_pbs_watch.ps1 -Action Stop`：停止本机监听。

## 登记与查询

在 VASP 项目内提交并记录当前可运行的 PBS 作业后，执行以下命令登记与查询：

```powershell
python scripts/pbs_watch.py add 52311.master relax Materials/examples/K2CrF4 --start
python scripts/pbs_watch.py status
```

- 在 Codex 环境中默认绑定当前聊天 UUID；在其他终端执行时可通过 `--thread <VASP 聊天 UUID>` 显式指定。
- 登记时会核对聊天对应的项目路径，查询时会核对 PBS 作业名、账号和算例路径。
- `add --start` 在登记后按需启动已安装的 Windows 任务；单独执行 `add` 仅登记，后续可通过 `-Action Start` 启动监听。

## 事件机制与运行边界

- **启动告警（`startup`）**：包含算例、作业 ID、当时 PBS 状态与原因。当派发次数达到 2 次仍未建立执行会话，或连续观测到 `R/41` 至少 4 分钟时，监听器会按需调用 `tracejob` 查询节点与拒绝原因（普通排队仅在查到派发失败记录时才告警）。每个作业的启动告警仅回传一次，随后继续追踪终态。
- **终态回传**：包含算例、作业 ID、PBS 状态与退出码。监听器本身不包含提交命令；收到回传后，由 Codex 重新核查 PBS 与计算输出，确认收敛及产物无误后再提交下一步。
- **Codex 额度保护**：自动投递前会检查目标聊天最近记录的 Codex 周额度。若额度耗尽、记录已过重置时间或无法读取，事件将保留为本机 `pending`，不影响 PBS 作业继续运行；待正常会话产生新的额度记录后再恢复投递（该检查基于本机最近记录，账户并发使用可能先于记录更新）。
- **状态持久与限额**：状态文件与轮转日志保存在 `%LOCALAPPDATA%\CodexVaspPbs`。短时断线、缺少作业记录或终态尚缺退出码时，保留上一次可信状态。单次 SSH 最多查询 16 个作业（子进程输出上限 1 MiB），单条回传最多合并 16 个事件（投递子进程输出上限 16 KiB）；超限查询保留此前状态，回执不明确的投递记为 `sending` 供人工核对。

## 投递通道与回执状态

- **主通道（`codex-ipc`）**：计划任务优先通过 Codex Desktop 本机 IPC 投递至已登记聊天。活动轮次会直接引导，空闲且仍由 Desktop 持有的聊天会直接启动下一轮。若 IPC 明确报告原聊天无接收端，监听器会通过 `codex://threads/<UUID>` 自动打开原聊天并重试一次（Desktop 可能切换至该聊天，每个待回传事件最多自动打开一次）；若仍不可用则保留 `pending` 并按原间隔重试。
- **备选通道（`codex-app-tools` MCP）**：当桌面端仅提供 `codex-app-tools` 管道时，监听器在核验所属进程、Windows 会话与代理后，通过随 Desktop 安装的 MCP 服务调用 `send_message_to_thread`，并在原聊天记录中核对事件全文与接收轮次。无可用通道时保留 `pending`，投递后回执不明时保留 `sending`。
- **代理启动说明**：通过 Windows 通知直接唤起的进程可能绕过 Codex 专用代理启动器，请始终使用原代理启动器启动 Codex，并以轮次回执及聊天记录作为回传验收依据。
- **状态说明**：
  - `steered`：已确认引导至当前活动轮次（`detail` 记录对应轮次 ID）。
  - `started`：已确认启动新轮次（`detail` 记录对应轮次 ID）。
  - `received`：通过 MCP 通道投递且已在原聊天记录中核实接收轮次（非活动轮引导）。
  - `queued`：旧版状态，表示 CLI 已接受排队。
  - `pending`：本机待投递或待重试。
  - `sending`：投递中断或回执不明确，需核对后再决定是否重试。
- **实测记录（2026-11-13）**：Windows 托盘实测覆盖活动与空闲两种状态——活动聊天收到 `steered` 并保留原轮次 ID；空闲聊天于 21:55 收到 `started`，聊天记录确认测试消息仅进入一次新轮次，测试前后均由同一带代理的 Desktop 进程持有 IPC，无排队、弹窗或新增 Desktop 进程。

## 事件确认与失败恢复

- 处理完已回传事件后，运行以下命令确认消警：
  ```powershell
  python scripts/pbs_watch.py ack <event_id>
  ```
- 若事件停留在 `sending`，请先核对原聊天、PBS 状态及算例作业记录；确认原聊天未收到后，再执行以下命令重新入队并启动监听：
  ```powershell
  python scripts/pbs_watch.py retry <event_id>
  ```
- Codex Desktop 更新后，建议复测本机 IPC 投递兼容性。
