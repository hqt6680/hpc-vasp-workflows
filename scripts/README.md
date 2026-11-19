# VASP PBS 作业回传

监听器只处理显式登记的 zjt PBS 作业。它每 120 秒通过 SSH 查询同批作业，断线时逐步延长到 15 分钟。启动告警、带退出码的 PBS 终态及已确认的未启动撤回会回传到原 VASP 聊天。同一算例同次查到的事件会合并发送。全部作业结束且没有待发送事件时，监听器自动退出。

## 登记和查询

在 VASP 项目内提交并记录当前可运行的 PBS 作业，再执行以下命令。Codex 环境默认用当前聊天 UUID，其他终端可传 `--thread <VASP 聊天 UUID>`。登记时核对聊天的项目路径，查询时核对 PBS 作业名、账号和算例路径。

```powershell
python scripts/pbs_watch.py add 52311.master relax Materials/examples/K2CrF4 --start
python scripts/pbs_watch.py status
```

首次使用需要 Python 和 Node.js，执行 `.\scripts\install_pbs_watch.ps1 -Action Install -ResumeAtLogon`。`add --start` 登记后按需启动已安装的 Windows 任务。单独运行 `add` 只登记，可以用 `-Action Start` 恢复待处理作业。计划任务没有周期触发。可选的登录触发用于恢复已有工作，无工作时立即退出，不查询 PBS。用 `-Action Status` 查看监听器，用 `-Action Stop` 停止本机监听。

## 验收和恢复

- 启动告警含算例、作业 ID、当时的 PBS 状态和原因，事件类型为 `startup`。派发次数达到两次且仍未建立执行会话，或连续观测到 `R/41` 至少四分钟时，监听器按需用 `tracejob` 查节点和拒绝原因。普通排队须查到派发失败记录才告警。每个作业的启动告警只回传一次，随后继续追踪终态。
- 终态回传含算例、作业 ID、PBS 状态和退出码。Codex 重新查 PBS 及计算输出，验收收敛和对应文件后才提交下一步。监听器无提交命令。
- 自动投递前读取目标聊天最近记录的 Codex 周额度。周额度耗尽、记录已过重置时间或无法读取时，事件保留为本机 pending，PBS 作业继续运行。额度恢复后由正常会话产生新的额度记录，再继续处理待回传事件。此检查使用本机最近记录，账户并发使用可能先于记录更新。
- 状态和轮转日志保存在 `%LOCALAPPDATA%\CodexVaspPbs`。短时断线、缺少作业记录或终态尚缺退出码时保留上一次可信状态。
- 每次 SSH 最多查询 16 个作业，子进程输出上限 1 MiB。每条回传最多 16 个事件，投递子进程输出上限 16 KiB。超过上限的查询保留此前状态，回执不明确的投递保留为 `sending` 供核对。
- 回传通过 Codex Desktop 本机 IPC 投给已登记聊天。已有活动轮时直接引导，空闲且仍由 Desktop 持有的聊天会直接启动下一轮。Desktop 暂不可达或尚未接管聊天时，事件留在本机 `pending`，监听器按原间隔重试。此时无需重复登记作业。
- 2026-11-13 Windows 托盘实测覆盖两种状态。活动聊天收到 `steered` 并保留原轮次 ID。空闲聊天在 21:55 收到 `started`，聊天记录确认测试消息只进入一次新轮次。空闲测试前后均由同一带代理的 Desktop 进程持有 IPC，没有排队、弹窗或新增 Desktop 进程。
- Windows 计划任务直接运行 `pbs_watch.py`。正式回传调用与托盘实测相同的 `desktop_delivery.mjs`，只连接现有的 `codex-ipc`。本项目在发送前核对 IPC 所属 Desktop 的 `--proxy-server` 值。该实例不可用时，事件保留为本机 `pending`，按原间隔重试。
- Windows 通知启动的进程可能不经过 Codex 专用代理启动器。只用原来的代理启动器启动 Codex，回传验收以轮次回执和聊天记录为准。
- `steered` 与 `started` 分别表示 Desktop 已确认引导或启动，`detail` 保存对应轮次 ID。旧版 `queued` 表示 CLI 接受了排队。处理事件后运行 `python scripts/pbs_watch.py ack <event_id>`。
- 投递中断或回执不明时保留 `sending`。确认原聊天未收到后，再执行 `python scripts/pbs_watch.py retry <event_id>` 并启动监听。重试前核对 PBS 和算例作业记录。Desktop 更新后需复测本机 IPC 的兼容性。
