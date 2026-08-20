<#
.SYNOPSIS
    把 xhs-agent 的技能装到 Codex CLI 能找到的地方（Windows）。

.DESCRIPTION
    Codex 会从这些位置发现 skills：
        %USERPROFILE%\.codex\skills\      ← Codex 原生路径
        %USERPROFILE%\.agents\skills\     ← 跨 agent 通用路径
        <仓库根>\.agents\skills\           ← 项目级（在仓库内工作时自动生效）

    默认用**目录联接（junction）**指向仓库里的 skills\，好处是 git pull 之后
    技能自动更新，不用重装。junction 在 Windows 上不需要管理员权限。

.PARAMETER Mode
    link（默认）用 junction；copy 用复制（跨盘或不支持 junction 时用）。

.PARAMETER Uninstall
    移除装进去的技能。

.EXAMPLE
    .\install.ps1
    .\install.ps1 -Mode copy
    .\install.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [ValidateSet('link', 'copy')]
    [string]$Mode = 'link',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$Repo = $PSScriptRoot
$SkillsSrc = Join-Path $Repo 'skills'

if (-not (Test-Path $SkillsSrc)) {
    Write-Error "找不到 $SkillsSrc —— 请在仓库根目录运行这个脚本。"
}

# Codex 的两个用户级技能目录，都装上，避免版本差异导致找不到
$Targets = @(
    (Join-Path $HOME '.codex\skills'),
    (Join-Path $HOME '.agents\skills')
)

$Skills = Get-ChildItem -Directory $SkillsSrc | Where-Object {
    Test-Path (Join-Path $_.FullName 'SKILL.md')
}

if ($Skills.Count -eq 0) {
    Write-Error "$SkillsSrc 下没有找到含 SKILL.md 的技能目录。"
}

Write-Host ''
Write-Host '  xhs-agent · 小红书创作技能包' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────' -ForegroundColor DarkGray
Write-Host "  仓库：$Repo"
Write-Host "  技能：$($Skills.Count) 个 —— $(($Skills.Name) -join ', ')"
Write-Host ''

# ---------------------------------------------------------------- 卸载
if ($Uninstall) {
    $n = 0
    foreach ($t in $Targets) {
        foreach ($s in $Skills) {
            $link = Join-Path $t $s.Name
            if (Test-Path $link) {
                # junction 用 Directory.Delete 移除，不会跟进去删源文件
                $item = Get-Item $link -Force
                if ($item.LinkType) { [System.IO.Directory]::Delete($link, $false) }
                else { Remove-Item $link -Recurse -Force }
                Write-Host "  ✓ 移除 $link" -ForegroundColor DarkGray
                $n++
            }
        }
    }
    Write-Host ''
    Write-Host "  已移除 $n 项。" -ForegroundColor Green
    Write-Host ''
    exit 0
}

# ---------------------------------------------------------------- 安装
foreach ($t in $Targets) {
    if (-not (Test-Path $t)) {
        New-Item -ItemType Directory -Force -Path $t | Out-Null
    }
    Write-Host "  → $t" -ForegroundColor Yellow

    foreach ($s in $Skills) {
        $link = Join-Path $t $s.Name

        if (Test-Path $link) {
            $item = Get-Item $link -Force
            if ($item.LinkType) { [System.IO.Directory]::Delete($link, $false) }
            else { Remove-Item $link -Recurse -Force }
        }

        if ($Mode -eq 'link') {
            try {
                New-Item -ItemType Junction -Path $link -Target $s.FullName -ErrorAction Stop | Out-Null
                Write-Host "      ✓ $($s.Name)  (junction)" -ForegroundColor Green
            }
            catch {
                Copy-Item $s.FullName $link -Recurse -Force
                Write-Host "      ✓ $($s.Name)  (junction 失败，已改为复制)" -ForegroundColor DarkYellow
            }
        }
        else {
            Copy-Item $s.FullName $link -Recurse -Force
            Write-Host "      ✓ $($s.Name)  (复制)" -ForegroundColor Green
        }
    }
}

# ---------------------------------------------------------------- 环境自检
Write-Host ''
Write-Host '  环境自检' -ForegroundColor Cyan
Write-Host '  ─────────' -ForegroundColor DarkGray

$py = $null
foreach ($c in @('python', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if ($py) {
    $ver = (& $py --version 2>&1) -join ''
    Write-Host "  ✓ Python：$ver" -ForegroundColor Green
}
else {
    Write-Host '  ✗ 找不到 Python —— 合规扫描、语气统计、字幕生成都需要它' -ForegroundColor Red
    Write-Host '    装一个：https://www.python.org/downloads/' -ForegroundColor DarkGray
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($codex) {
    Write-Host "  ✓ Codex CLI：$($codex.Source)" -ForegroundColor Green
}
else {
    Write-Host '  ! 没找到 codex 命令（如果你只在 Claude Code 里用，可以忽略）' -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------- 冒烟测试
Write-Host ''
Write-Host '  冒烟测试' -ForegroundColor Cyan
Write-Host '  ─────────' -ForegroundColor DarkGray
if ($py) {
    $scan = Join-Path $Repo 'skills\xhs-guard\scripts\xhs_scan.py'
    & $py $scan --text '这家店最好吃，私我拿地址' --min-tier L2 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 1) {
        Write-Host '  ✓ 合规扫描器工作正常（正确拦下了测试用的违规文案）' -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ 合规扫描器异常（期望 exit 1，实际 $LASTEXITCODE）" -ForegroundColor Red
    }
}

# ---------------------------------------------------------------- 下一步
Write-Host ''
Write-Host '  装好了。接下来：' -ForegroundColor Cyan
Write-Host ''
Write-Host '  1. 把你发过的笔记放进 samples\（一篇一个 .md，越多越准）'
Write-Host '  2. 开 codex，说「学一下我的语气」→ 会生成 profile\voice.md'
Write-Host '  3. 然后就可以说「帮我写篇笔记」「做个封面」「审一下这个文案」'
Write-Host ''
Write-Host '  Claude Code 用户：这个仓库同时是一个 plugin，' -ForegroundColor DarkGray
Write-Host "  在 Claude Code 里把 $Repo 添加为本地 plugin 即可。" -ForegroundColor DarkGray
Write-Host ''
