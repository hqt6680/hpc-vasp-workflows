---
name: vasp-pbs
description: 部署 VASP 工作区，选择组内知识库和 AICC，按用户指定的服务器目录学习个人计算方法，并在 Windows 回传已登记的 PBS 作业。
---

# VASP 参考与 PBS 作业回传

## 查阅组内资料

首次部署按[知识库设置](references/setup.md#知识库设置)分别询问是否使用默认组内知识库、是否现在指定个人学习目录，然后执行 `scripts/setup_workspace.py` 初始化指定的工作根。以后对话先读取当前 Windows 项目的 `.vasp-local/knowledge.md`，进入已配置的远程工作根读 `AGENTS.md`。收到“学习这个目录”时追加到 `knowledge/personal/`。

使用默认库时，按[实时读取组内知识库](references/group-library.md)从服务器选择教程、枚举算例并读取其流程文档。AICC 提供准备、预检和验收工具。普通计算使用本人的远程工作目录，按实际输入记录版本、参数和与示例的差异。

## 使用项目监听器

首次使用按 [配置和安装](references/setup.md) 部署项目脚本。使用接收者自己的 SSH 配置、集群账号、算例路径和 Codex Desktop。

1. 只登记已提交且需要等待的 PBS 作业，绑定当前项目聊天。登记后启动本机监听。监听器批量查询并在没有待处理记录时退出。
2. 回传到达后按项目规则通过 SSH 复核 PBS 作业 ID、账号、工作目录、状态和退出码。PBS 完成后再按站点及算例要求核验计算输出。
3. 核对已有作业记录，避免重复提交。只有在授权范围内、前置计算验收后，才提交当前可运行的下一步。处理完事件后执行 `python scripts/pbs_watch.py ack <event_id>`。
4. `sending` 表示投递结果未确认。检查原聊天后再决定是否执行 `retry`。具体命令及状态含义见安装说明。
