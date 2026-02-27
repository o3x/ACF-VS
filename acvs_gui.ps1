Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# メインフォームの作成
$form = New-Object Windows.Forms.Form
$form.Text = "ACF-VS (Anime Cut Folder Versioning System) GUI"
$form.Size = New-Object Drawing.Size(800, 600)
$form.StartPosition = "CenterScreen"
$form.BackColor = [System.Drawing.Color]::White

# フォント設定
$font_main = New-Object System.Drawing.Font("Meiryo UI", 10)
$font_bold = New-Object System.Drawing.Font("Meiryo UI", 10, [System.Drawing.FontStyle]::Bold)
$font_console = New-Object System.Drawing.Font("Consolas", 10)
$form.Font = $font_main

# --- コントロールの配置 ---

# 1. Root Directory 選択部
$labelRoot = New-Object Windows.Forms.Label
$labelRoot.Text = "エピソードルート (Root Dir):"
$labelRoot.Location = New-Object Drawing.Point(20, 20)
$labelRoot.AutoSize = $true
$form.Controls.Add($labelRoot)

$txtRoot = New-Object Windows.Forms.TextBox
$txtRoot.Location = New-Object Drawing.Point(20, 45)
$txtRoot.Size = New-Object Drawing.Size(600, 25)
# 実行しているディレクトリを初期値にする
$txtRoot.Text = (Get-Location).Path
$form.Controls.Add($txtRoot)

$btnBrowse = New-Object Windows.Forms.Button
$btnBrowse.Text = "参照..."
$btnBrowse.Location = New-Object Drawing.Point(630, 43)
$btnBrowse.Size = New-Object Drawing.Size(130, 28)
$btnBrowse.BackColor = [System.Drawing.Color]::LightGray
$form.Controls.Add($btnBrowse)

# 2. カット番号入力部
$labelCut = New-Object Windows.Forms.Label
$labelCut.Text = "カット番号 (例: c001):"
$labelCut.Location = New-Object Drawing.Point(20, 90)
$labelCut.AutoSize = $true
$form.Controls.Add($labelCut)

$txtCut = New-Object Windows.Forms.TextBox
$txtCut.Location = New-Object Drawing.Point(180, 87)
$txtCut.Size = New-Object Drawing.Size(150, 25)
$txtCut.Text = "test_env" # テスト用初期値
$form.Controls.Add($txtCut)

# 3. アクションボタン
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


# 4. 出力表示エリア
$labelOutput = New-Object Windows.Forms.Label
$labelOutput.Text = "出力 (Output):"
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

# --- イベントの設定 ---

$python_script = Join-Path -Path $PSScriptRoot -ChildPath "acvs_core.py"

function Get-TargetDir {
    $rootDir = $txtRoot.Text
    $cutDir = $txtCut.Text
    if ([string]::IsNullOrWhiteSpace($cutDir)) { return $rootDir }
    return Join-Path -Path $rootDir -ChildPath $cutDir
}

function Run-ACVSCommand {
    param([string]$command)
    
    $targetDir = Get-TargetDir
    
    if (-not (Test-Path $targetDir)) {
        $txtOutput.Text = "Error: Directory not found -> $targetDir"
        return
    }
    
    $txtOutput.Text = "Running ACF-VS $command on $targetDir ...`r`n`r`n"
    
    $args = @($command, "--dir", "`"$targetDir`"")
    if ($chkFast.Checked) { $args += "--fast" }
    if ($chkSeq.Checked) { $args += "--seq" }
    
    $fullArgs = $args -join " "
    
    try {
        # output encoding setting for windows
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
        $process.WaitForExit()
        
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        
        if ($stdout) { $txtOutput.Text += $stdout }
        if ($stderr) { $txtOutput.Text += "ERROR:`r`n" + $stderr }
        
        # 改行コードの調整（Windowsコントロール用）
        $txtOutput.Text = $txtOutput.Text -replace "`r`n", "`n" -replace "`r", "`n" -replace "`n", "`r`n"
        
    } catch {
        $txtOutput.Text += "Failed to execute python script. Make sure python is in PATH and acvs_core.py exists next to this script."
    }
}

# 参照ボタンの動作
$btnBrowse.Add_Click({
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    $dialog.Description = "エピソードルートフォルダを選択してください"
    $dialog.SelectedPath = $txtRoot.Text
    if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        $txtRoot.Text = $dialog.SelectedPath
    }
})

# Scan(Status)ボタンの動作
$btnStatus.Add_Click({
    Run-ACVSCommand -command "status"
})

# Commitボタンの動作
$btnCommit.Add_Click({
    Run-ACVSCommand -command "commit"
})

# Logボタンの動作
$btnLog.Add_Click({
    Run-ACVSCommand -command "log"
})

# EnterキーでScanを実行する便利機能
$txtCut.Add_KeyDown({
    if ($_.KeyCode -eq "Enter") {
        Run-ACVSCommand -command "status"
    }
})

# フォームの表示
$form.ShowDialog() | Out-Null
