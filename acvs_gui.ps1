# Version: 0.2.12
# Last Updated: Sun Mar 01 18:25:56 JST 2026

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

$progressBar = New-Object Windows.Forms.ProgressBar
$progressBar.Location = New-Object Drawing.Point(20, 545)
$progressBar.Size = New-Object Drawing.Size(740, 20)
$progressBar.Style = "Continuous"
$progressBar.Value = 0
$form.Controls.Add($progressBar)

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
    param([string]$command, [bool]$isRetry = $false)
    
    $targetDir = Get-TargetDir
    if (-not (Test-Path $targetDir)) {
        $txtOutput.Text = "Error: Directory not found -> $targetDir"
        return
    }
    
    Set-UIState -enabled $false
    if (-not $isRetry) { $txtOutput.Clear() }
    $txtOutput.AppendText("Running ACF-VS $command on $targetDir ...`r`n")
    $progressBar.Value = 0
    
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
        
        # PythonにUTF-8での出力を強制する
        $processInfo.EnvironmentVariables["PYTHONUTF8"] = "1"
        $processInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        $process.Start() | Out-Null
        
        $missingManifest = $false
        
        while (-not $process.HasExited) {
            while ($line = $process.StandardOutput.ReadLine()) {
                if ($line -match "PROGRESS: (\d+)/(\d+)") {
                    $current = [int]$matches[1]
                    $total = [int]$matches[2]
                    $progressBar.Maximum = $total
                    $progressBar.Value = $current
                }
                elseif ($line -match "Fatal: .*\.cut_manifest\.json not found") {
                    $missingManifest = $true
                    $txtOutput.AppendText($line + "`r`n")
                }
                else {
                    $txtOutput.AppendText($line + "`r`n")
                }
                [System.Windows.Forms.Application]::DoEvents()
            }
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 50
        }
        
        $stderr = $process.StandardError.ReadToEnd()
        if ($stderr) { 
            if ($stderr -match "not found") { $missingManifest = $true }
            $txtOutput.AppendText("`r`nERROR:`r`n" + $stderr) 
        }
        
        if ($missingManifest -and $command -ne "init") {
            $msg = "このディレクトリはまだACF-VSで管理されていません。`r`n初期化（Init）して管理を開始しますか？"
            $result = [System.Windows.Forms.MessageBox]::Show($msg, "初期化の確認", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question)
            if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
                Invoke-ACVSCommand -command "init" -isRetry $true
                return
            }
        }

        $txtOutput.AppendText("`r`nDone.")
        $progressBar.Value = $progressBar.Maximum
    }
    catch {
        $txtOutput.AppendText("`r`nFailed to execute python script.")
    }
    finally {
        Set-UIState -enabled $true
    }
}

# 参照ボタンの動作
$btnBrowse.Add_Click({
        $dialog = New-Object Windows.Forms.OpenFileDialog
        $dialog.Title = "エピソードルートフォルダを選択してください"
        $dialog.CheckFileExists = $false
        $dialog.CheckPathExists = $true
        $dialog.FileName = "Folder Selection"
        $dialog.Filter = "Folders|*.none"
        $dialog.InitialDirectory = $txtRoot.Text
        if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
            $txtRoot.Text = [System.IO.Path]::GetDirectoryName($dialog.FileName)
        }
    })

# Scan(Status)ボタンの動作
$btnStatus.Add_Click({
        Invoke-ACVSCommand -command "status"
    })

# Commitボタンの動作
$btnCommit.Add_Click({
        Invoke-ACVSCommand -command "commit"
    })

# Logボタンの動作
$btnLog.Add_Click({
        Invoke-ACVSCommand -command "log"
    })

# EnterキーでScanを実行する便利機能
$txtCut.Add_KeyDown({
        if ($_.KeyCode -eq "Enter") {
            Invoke-ACVSCommand -command "status"
        }
    })

# フォームの表示
$form.ShowDialog() | Out-Null
