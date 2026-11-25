---
name: vasp-pbs
description: 部署或恢复本机 VASP 工作区，选择组内知识库和 AICC，按用户指定的服务器目录学习个人计算方法，并在 Windows 回传已登记的 PBS 作业。
---

# VASP 参考与 PBS 作业回传

用户要求“恢复本机”或卸载时，按[恢复本机](references/setup.md#恢复本机)在用户指定的 Windows 项目执行恢复命令。这个操作只在本机运行。

## 查阅组内资料

部署时按[配置和安装](references/setup.md)先验证已选 SSH 入口。缺少别名时逐卡配置并保存，已有入口只缺免密认证时沿用该入口登记公钥。验证免交互复连后，再收集工作根、知识库和回传选择。每个缺项调用一次问答卡工具，只放一个问题，等用户实际回复后再发下一张。已有答案直接沿用。

从解压包执行 `scripts/setup_workspace.py` 初始化指定的工作根。以后对话先读取当前 Windows 项目的 `.vasp-local/knowledge.md`，进入已配置的远程工作根读 `AGENTS.md`。收到“学习这个目录”时追加到 `knowledge/personal/`。

使用默认库时，按[SSH 读取入口](references/group-library.md)从 `Master/README.md` 选方法，在 `Master/case_index.md` 按目标物理量、结构和磁态选已验收算例。读取该例的 `workflow.md`，在用户工作目录按“输入与关键参数 → 执行 → 验收 → 结果文件”复算。用 AICC 做预检和验收。

维护参考文档时，只写可复用的标准流程和实测参数。未验收条目列入“待建设”。查询运行或续算状态时读算例的 PBS 作业表。

## 使用项目监听器

首次使用按 [配置和安装](references/setup.md) 部署项目脚本。使用接收者自己的 SSH 配置、集群账号、算例路径和 Codex Desktop。

1. 只登记已提交且需要等待的 PBS 作业，绑定当前项目聊天。登记后启动本机监听。监听器批量查询并在没有待处理记录时退出。
2. 回传到达后按项目规则通过 SSH 复核 PBS 作业 ID、账号、工作目录、状态和退出码。PBS 完成后再按站点及算例要求核验计算输出。
3. 核对已有作业记录，避免重复提交。只有在授权范围内、前置计算验收后，才提交当前可运行的下一步。处理完事件后执行 `python scripts/pbs_watch.py ack <event_id>`。
4. `sending` 表示投递结果未确认。检查原聊天后再决定是否执行 `retry`。具体命令及状态含义见安装说明。
