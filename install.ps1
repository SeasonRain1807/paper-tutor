<#
.SYNOPSIS
    把 paper-tutor 安装到 DSH / Claude Code / Codex / 通用 Agent Skills 目录。

.DESCRIPTION
    skill 本体始终是本仓库的 skills/paper-tutor。本脚本只在目标位置建立
    目录链接（Windows 为 junction，不需要管理员权限），或用 -Copy 复制一份副本。
    不会修改本仓库内的任何文件。

.NOTES
    本文件必须以 **UTF-8 带 BOM** 保存：Windows PowerShell 5.1 用 -File 调用时
    按 ANSI 代码页读取脚本，没有 BOM 会把中文注释读成乱码并抛语法错误。

.PARAMETER Hosts
    要安装的宿主，逗号分隔：dsh, claude, codex, agents。all 等于全部。
    默认 claude,codex；加 -Uninstall 时默认 all（把装过的都清掉）。

.PARAMETER Scope
    project（默认）装到 -Target 指定的项目目录；user 装到用户主目录。

.PARAMETER Target
    项目根目录，默认本仓库根目录。

.PARAMETER Copy
    复制而不是建立链接。

.PARAMETER Uninstall
    删除本脚本建立过的安装项（只删名为 paper-tutor 的目录）。

.EXAMPLE
    .\install.ps1 -Hosts all

.EXAMPLE
    .\install.ps1 -Scope user -Hosts claude,codex -Copy

.EXAMPLE
    .\install.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string[]]$Hosts = @('claude', 'codex'),
    [ValidateSet('project', 'user')]
    [string]$Scope = 'project',
    [string]$Target = '',
    [switch]$Copy,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

# PowerShell 5.1 用 -File 调用时，param 默认值里的 $PSScriptRoot 还是空的；这里补上
if ([string]::IsNullOrWhiteSpace($Target)) { $Target = $PSScriptRoot }

# 卸载时默认覆盖全部宿主，避免 -Hosts all 装完却只清掉 claude/codex
if ($Uninstall -and -not $PSBoundParameters.ContainsKey('Hosts')) { $Hosts = @('all') }

$SkillName = 'paper-tutor'
$Source    = Join-Path $PSScriptRoot "skills\$SkillName"

# 各宿主的相对目录；user 为 $null 表示不支持用户级
$HostDirs = [ordered]@{
    'dsh'    = @{ label = 'DeepSeek Harness (DSH)'; project = '.dsh\skills';    user = $null }
    'claude' = @{ label = 'Claude Code';            project = '.claude\skills'; user = '.claude\skills' }
    'codex'  = @{ label = 'Codex';                  project = '.codex\skills';  user = '.codex\skills' }
    'agents' = @{ label = 'Agent Skills 通用目录';  project = '.agents\skills'; user = '.agents\skills' }
}

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "找不到 skill 本体：$Source（请在仓库根目录运行本脚本）"
}

$selected = @()
foreach ($h in $Hosts) {
    foreach ($part in ($h -split ',')) {
        $name = $part.Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if ($name -eq 'all') { $selected += $HostDirs.Keys; continue }
        if (-not $HostDirs.Contains($name)) {
            throw "未知宿主：$name（可选：dsh, claude, codex, agents, all）"
        }
        $selected += $name
    }
}
$selected = @($selected | Select-Object -Unique)
if ($selected.Count -eq 0) { throw '没有选中任何宿主' }

$baseRoot = if ($Scope -eq 'user') { $HOME } else { (Resolve-Path -LiteralPath $Target).Path }

function Get-IsLink([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    return [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
}

$done = 0
$created = 0
foreach ($name in $selected) {
    $meta = $HostDirs[$name]
    $rel  = if ($Scope -eq 'user') { $meta.user } else { $meta.project }

    if ([string]::IsNullOrEmpty($rel)) {
        Write-Warning "$($meta.label) 只支持项目级安装（.dsh/skills），已跳过"
        continue
    }

    $base = Join-Path $baseRoot $rel
    $dest = Join-Path $base $SkillName

    # 目标就是 skill 本体本身（在仓库里装 DSH 项目级）：跳过，绝不删除
    if (([System.IO.Path]::GetFullPath($dest).TrimEnd('\')) -eq ([System.IO.Path]::GetFullPath($Source).TrimEnd('\'))) {
        if ($Uninstall) { Write-Host "跳过：$dest 就是 skill 本体本身，未删除" }
        else           { Write-Host "已就位（这就是 skill 本体）：$dest"; $done++ }
        continue
    }

    if ($Uninstall) {
        if (-not (Test-Path -LiteralPath $dest)) {
            Write-Host "未安装：$dest"
            continue
        }
        if (Get-IsLink $dest) {
            # 目录链接：只删链接本身，绝不动被链接的目标
            [System.IO.Directory]::Delete($dest, $false)
            Write-Host "已删除链接：$dest"
        }
        elseif ((Test-Path -LiteralPath (Join-Path $dest 'SKILL.md')) -and (Test-Path -LiteralPath (Join-Path $dest 'scripts'))) {
            Remove-Item -LiteralPath $dest -Recurse -Force
            Write-Host "已删除副本：$dest"
        }
        else {
            Write-Warning "跳过 $dest：看起来不是 paper-tutor 的安装目录，未删除任何东西"
        }
        $done++
        continue
    }

    if (Test-Path -LiteralPath $dest) {
        if ((Get-IsLink $dest) -and ((Get-Item -LiteralPath $dest -Force).Target -contains $Source)) {
            Write-Host "已是最新链接：$dest"
            $done++
            continue
        }
        if ((Test-Path -LiteralPath (Join-Path $dest 'SKILL.md')) -and (Test-Path -LiteralPath (Join-Path $dest 'scripts'))) {
            Write-Host "已存在副本：$dest（如需更新，先运行 -Uninstall 再装）"
        }
        else {
            Write-Warning "已存在 $dest，且不像 paper-tutor 的安装项（先手动确认再处理）"
        }
        continue
    }

    New-Item -ItemType Directory -Path $base -Force | Out-Null

    if ($Copy) {
        Copy-Item -LiteralPath $Source -Destination $dest -Recurse -Force
        Write-Host "已复制到：$dest"
        $done++
        $created++
        continue
    }

    try {
        New-Item -ItemType Junction -Path $dest -Target $Source | Out-Null
        Write-Host "已链接到：$dest"
        $done++
        $created++
    }
    catch {
        Copy-Item -LiteralPath $Source -Destination $dest -Recurse -Force
        Write-Host "链接失败（$($_.Exception.Message)），已改为复制到：$dest"
        $done++
        $created++
    }
}

if (-not $Uninstall -and $created -gt 0) {
    Write-Host ''
    Write-Host '装好了。触发方式：在会话里把论文交给 Agent，例如「帮我把这篇 paper.pdf 精读一遍」。'
    Write-Host '卸载：再运行一次本脚本并加 -Uninstall。'
}