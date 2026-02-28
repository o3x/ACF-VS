# Version: 0.2.4
# Last Updated: Sat Feb 28 15:00:24 JST 2026

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 繝｡繧､繝ｳ繝輔か繝ｼ繝縺ｮ菴懈・
$form = New-Object Windows.Forms.Form
$form.Text = "ACF-VS (Anime Cut Folder Versioning System) GUI"
$form.Size = New-Object Drawing.Size(800, 600)
$form.StartPosition = "CenterScreen"
$form.BackColor = [System.Drawing.Color]::White

# 繝輔か繝ｳ繝郁ｨｭ螳・
$font_main = New-Object System.Drawing.Font("Meiryo UI", 10)
$font_bold = New-Object System.Drawing.Font("Meiryo UI", 10, [System.Drawing.FontStyle]::Bold)
$font_console = New-Object System.Drawing.Font("Consolas", 10)
$form.Font = $font_main

# --- 繧ｳ繝ｳ繝医Ο繝ｼ繝ｫ縺ｮ驟咲ｽｮ ---

# 1. Root Directory 驕ｸ謚樣Κ
$labelRoot = New-Object Windows.Forms.Label
$labelRoot.Text = "繧ｨ繝斐た繝ｼ繝峨Ν繝ｼ繝・(Root Dir):"
$labelRoot.Location = New-Object Drawing.Point(20, 20)
$labelRoot.AutoSize = $true
$form.Controls.Add($labelRoot)

$txtRoot = New-Object Windows.Forms.TextBox
$txtRoot.Location = New-Object Drawing.Point(20, 45)
$txtRoot.Size = New-Object Drawing.Size(600, 25)
# 螳溯｡後＠縺ｦ縺・ｋ繝・ぅ繝ｬ繧ｯ繝医Μ繧貞・譛溷､縺ｫ縺吶ｋ
$txtRoot.Text = (Get-Location).Path
$form.Controls.Add($txtRoot)

$btnBrowse = New-Object Windows.Forms.Button
$btnBrowse.Text = "蜿ら・..."
$btnBrowse.Location = New-Object Drawing.Point(630, 43)
$btnBrowse.Size = New-Object Drawing.Size(130, 28)
$btnBrowse.BackColor = [System.Drawing.Color]::LightGray
$form.Controls.Add($btnBrowse)

# 2. 繧ｫ繝・ヨ逡ｪ蜿ｷ蜈･蜉幃Κ
$labelCut = New-Object Windows.Forms.Label
$labelCut.Text = "繧ｫ繝・ヨ逡ｪ蜿ｷ (萓・ c001):"
$labelCut.Location = New-Object Drawing.Point(20, 90)
$labelCut.AutoSize = $true
$form.Controls.Add($labelCut)

$txtCut = New-Object Windows.Forms.TextBox
$txtCut.Location = New-Object Drawing.Point(180, 87)
$txtCut.Size = New-Object Drawing.Size(150, 25)
$txtCut.Text = "test_env" # 繝・せ繝育畑蛻晄悄蛟､
$form.Controls.Add($txtCut)

# 3. 繧｢繧ｯ繧ｷ繝ｧ繝ｳ繝懊ち繝ｳ
$btnStatus = New-Object Windows.Forms.Button
$btnStatus.Text = "Scan (Status)"
$btnStatus.Location = New-Object Drawing.Point(20, 130)
$btnStatus.Size = New-Object Drawing.Size(150, 35)
$btnStatus.BackColor = [System.Drawing.Color]::LightBlue
$btnStatus.Font = $font_bold
$form.Controls.Add($btnStatus)

$btnCommit = New-Object Windows.Forms.Button
$btnCommit.Text = "Commit (Save)"
$btnCommit.Location = New-Object Drawing.Point(180, 130)
$btnCommit.Size = New-Object Drawing.Size(150, 35)
$btnCommit.BackColor = [System.Drawing.Color]::LightGreen
$btnCommit.Font = $font_bold
$form.Controls.Add($btnCommit)

$btnLog = New-Object Windows.Forms.Button
$btnLog.Text = "History Log"
$btnLog.Location = New-Object Drawing.Point(340, 130)
$btnLog.Size = New-Object Drawing.Size(150, 35)
$btnLog.BackColor = [System.Drawing.Color]::LightGoldenrodYellow
$btnLog.Font = $font_bold
$form.Controls.Add($btnLog)

$chkFast = New-Object Windows.Forms.CheckBox
$chkFast.Text = "Fast Mode (Size+Time)"
$chkFast.Location = New-Object Drawing.Point(510, 125)
$chkFast.AutoSize = $true
$chkFast.Checked = $true
$form.Controls.Add($chkFast)

$chkSeq = New-Object Windows.Forms.CheckBox
$chkSeq.Text = "Group Seq Images"
$chkSeq.Location = New-Object Drawing.Point(510, 145)
$chkSeq.AutoSize = $true
$chkSeq.Checked = $true
$form.Controls.Add($chkSeq)


# 4. 蜃ｺ蜉幄｡ｨ遉ｺ繧ｨ繝ｪ繧｢
$labelOutput = New-Object Windows.Forms.Label
$labelOutput.Text = "蜃ｺ蜉・(Output):"
$labelOutput.Location = New-Object Drawing.Point(20, 180)
$labelOutput.AutoSize = $true
$form.Controls.Add($labelOutput)

$txtOutput = New-Object Windows.Forms.TextBox
$txtOutput.Location = New-Object Drawing.Point(20, 205)
$txtOutput.Size = New-Object Drawing.Size(740, 330)
$txtOutput.Multiline = $true
$txtOutput.ScrollBars = "Vertical"
$txtOutput.Font = $font_console
$txtOutput.ReadOnly = $true
$txtOutput.BackColor = [System.Drawing.Color]::Black
$txtOutput.ForeColor = [System.Drawing.Color]::LightGreen
$form.Controls.Add($txtOutput)

# --- 繧､繝吶Φ繝医・險ｭ螳・---

$python_script = Join-Path -Path $PSScriptRoot -ChildPath "acvs_core.py"

function Get-TargetDir {
    $rootDir = $txtRoot.Text
    $cutDir = $txtCut.Text
    if ([string]::IsNullOrWhiteSpace($cutDir)) { return $rootDir }
    return Join-Path -Path $rootDir -ChildPath $cutDir
}

function Set-UIState {
    param([bool]$enabled)
    $btnStatus.Enabled = $enabled
    $btnCommit.Enabled = $enabled
    $btnLog.Enabled = $enabled
    $txtRoot.Enabled = $enabled
    $txtCut.Enabled = $enabled
    $btnBrowse.Enabled = $enabled
}

function Invoke-ACVSCommand {
    param([string]$command)
    
    $targetDir = Get-TargetDir
    
    if (-not (Test-Path $targetDir)) {
        $txtOutput.Text = "Error: Directory not found -> $targetDir"
        return
    }
    
    # UI縺ｮ辟｡蜉ｹ蛹厄ｼ井ｺ碁㍾螳溯｡碁亟豁｢・・
    Set-UIState -enabled $false
    $txtOutput.Text = "Running ACF-VS $command on $targetDir ...`r`n"
    $txtOutput.Text += "Please wait (GUI will remain responsive)...`r`n`r`n"
    
    $cmdArgs = @($command, "--dir", "`"$targetDir`"")
    if ($chkFast.Checked) { $cmdArgs += "--fast" }
    if ($chkSeq.Checked) { $cmdArgs += "--seq" }
    
    $fullArgs = $cmdArgs -join " "
    
    try {
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "python"
        $processInfo.Arguments = "`"$python_script`" $fullArgs"
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $processInfo.UseShellExecute = $false
        $processInfo.CreateNoWindow = $true
        $processInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $processInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        $process.Start() | Out-Null
        
        # 髱槫酔譛溷ｾ・■繝ｫ繝ｼ繝暦ｼ・oEvents縺ｧGUI繧貞虚縺九＠邯壹￠繧具ｼ・
        while (-not $process.HasExited) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        
        if ($stdout) { $txtOutput.Text += $stdout }
        if ($stderr) { $txtOutput.Text += "ERROR:`r`n" + $stderr }
        
        # 謾ｹ陦後さ繝ｼ繝峨・隱ｿ謨ｴ
        $txtOutput.Text = $txtOutput.Text -replace "`r`n", "`n" -replace "`r", "`n" -replace "`n", "`r`n"
        
    }
    catch {
        $txtOutput.Text += "Failed to execute python script. Make sure python is in PATH and acvs_core.py exists next to this script."
    }
    finally {
        # UI縺ｮ譛牙柑蛹・
        Set-UIState -enabled $true
    }
}

# 蜿ら・繝懊ち繝ｳ縺ｮ蜍穂ｽ・
$btnBrowse.Add_Click({
        $dialog = New-Object Windows.Forms.FolderBrowserDialog
        $dialog.Description = "繧ｨ繝斐た繝ｼ繝峨Ν繝ｼ繝医ヵ繧ｩ繝ｫ繝繧帝∈謚槭＠縺ｦ縺上□縺輔＞"
        $dialog.SelectedPath = $txtRoot.Text
        if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
            $txtRoot.Text = $dialog.SelectedPath
        }
    })

# Scan(Status)繝懊ち繝ｳ縺ｮ蜍穂ｽ・
$btnStatus.Add_Click({
        Invoke-ACVSCommand -command "status"
    })

# Commit繝懊ち繝ｳ縺ｮ蜍穂ｽ・
$btnCommit.Add_Click({
        Invoke-ACVSCommand -command "commit"
    })

# Log繝懊ち繝ｳ縺ｮ蜍穂ｽ・
$btnLog.Add_Click({
        Invoke-ACVSCommand -command "log"
    })

# Enter繧ｭ繝ｼ縺ｧScan繧貞ｮ溯｡後☆繧倶ｾｿ蛻ｩ讖溯・
$txtCut.Add_KeyDown({
        if ($_.KeyCode -eq "Enter") {
            Invoke-ACVSCommand -command "status"
        }
    })

# 繝輔か繝ｼ繝縺ｮ陦ｨ遉ｺ
$form.ShowDialog() | Out-Null

