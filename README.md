# VASP / PBS 工作流与技能包

| 入口 | 用途 |
| --- | --- |
| [scripts/](scripts/) | PBS 监听、Codex Desktop 回传与本机工作流辅助 |
| [share/vasp-pbs/SKILL.md](share/vasp-pbs/SKILL.md) | VASP / PBS 技能、资料与标准算例入口 |
| [最新技能安装包](https://github.com/hqt6680/hpc-vasp-workflows/releases/latest) | 下载 `vasp-pbs-skill.zip` 后按包内说明加载 |

LLG、MC 和 TB2J 脚本使用 zjt 服务器的 `Master/Simulation` 主目录。入口和同步规则见 [AGENTS.md](AGENTS.md) 与[自旋模拟入口](share/vasp-pbs/references/Master/Simulation/README.md)。

重新打包运行 `python scripts/package_vasp_pbs.py <输出路径>`。技能包包含离线副本需要的 PBS 脚本。VASP、赝势和计算输入在各自集群环境准备。

本机 PBS 监听的安装、验证和回退见 [HANDOFF.md](HANDOFF.md)。

## 在 VS Code 中连接 zjt

Windows 上的 VS Code 和 PowerShell 都可以使用 `%USERPROFILE%\.ssh\config`。已有内网地址的条目时，在同一行加上 `zjt` 别名即可。

```sshconfig
Host 10.100.0.222 zjt
    HostName 10.100.0.222
    User zjt
    Port 22
```

**使用远程终端。** 在 VS Code 的“终端 → 新建终端”中运行 `ssh zjt`，在密码提示处输入 SSH 密码。登录后运行以下命令进入项目并核对环境。

```bash
cd /public/home/zjt/task/now/hqt && whoami && hostname && pwd -P && cat AGENTS.md
```

**打开远程文件树。** 在 VS Code 中按 `Ctrl+Shift+P`，运行 `Remote-SSH: Connect to Host...`，选择 `10.100.0.222` 并在弹窗输入密码。左下角显示 `SSH: 10.100.0.222` 后，选择“文件 → 打开文件夹”，输入 `/public/home/zjt/task/now/hqt`。也可以从本机 PowerShell 直接打开该目录。

```powershell
code --new-window --folder-uri "vscode-remote://ssh-remote+10.100.0.222/public/home/zjt/task/now/hqt"
```

**本站的版本限制。** 内网入口 `master` 实测为 CentOS 7、内核 3.10、glibc 2.17。VS Code Server 1.147.0 使用公共 CP2K 目录 `/public/software/cp2k-2023/cp2k-2023.1/usr/lib/x86_64-linux-gnu` 提供的 glibc 2.35 和 libstdc++。已在这个版本验证 Remote - SSH 连接、远程项目文件、终端和搜索工具。宿主内核仍低于微软列出的 4.18 基线。[微软的 Linux 运行要求](https://code.visualstudio.com/docs/remote/faq#_can-i-run-vs-code-server-on-older-linux-distributions)

本机沿用 `remote.SSH.useExecServer = false`。已适配的服务端位于 `~/.vscode-server/bin/8a14f0cc1b08d531eb83255ea3764ae22aa932b5`，其 Node 使用上述目录中的动态加载器和库。桌面版更新后，可用 `code --version` 查看新的提交号；Remote - SSH 会按新提交号选择服务端目录，需要对新版本重新验证。若日志停在 `Copying file to remote` 后的密码提示，在 VS Code 弹窗输入 SSH 密码即可继续上传。
