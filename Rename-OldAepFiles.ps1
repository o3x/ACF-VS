<#
.SYNOPSIS
    (old)フォルダ内の特定の.aepファイルをリネームします。
.DESCRIPTION
    指定したベースパスの直下のサブフォルダ内にある「(old)」フォルダを検索し、
    条件に合致するAfter Effectsプロジェクトファイル(.aep)に更新日時を付与してリネームします。
    ファイル末尾が "_[tk]" と任意の2文字であるファイルが対象です。
.PARAMETER BasePath
    検索の起点となるディレクトリのパスです。指定しない場合はカレントディレクトリになります。
.EXAMPLE
    .\Rename-OldAepFiles.ps1 -BasePath "C:\Project" -WhatIf
    Dry Run（テスト実行）モードで実行します。変更予定のファイルが一覧表示されます。
.EXAMPLE
    .\Rename-OldAepFiles.ps1 -BasePath "C:\Project"
    本番実行（リネーム処理）を行います。
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param (
	[Parameter(Mandatory = $false, Position = 0)]
	[string]$BasePath = "."
)

# パスの解決と存在確認
try {
	$resolvedBasePath = (Resolve-Path $BasePath -ErrorAction Stop).Path
}
catch {
	Write-Host "指定されたパスが見つかりません: $BasePath" -ForegroundColor Red
	Read-Host "`nEnterキーを押して終了します"
	exit 1
}

Write-Host "==========================================" -ForegroundColor Cyan
if ($PSBoundParameters.ContainsKey('WhatIf') -and $PSBoundParameters['WhatIf']) {
	Write-Host "[モード] Dry Run (テスト実行) - 実際のファイル変更は行われません" -ForegroundColor Yellow
}
else {
	Write-Host "[モード] Execute (本番実行) - ファイルの変更を行います" -ForegroundColor Red
}
Write-Host "[対象パス] $resolvedBasePath" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1階層下のフォルダを取得 (「ベースパスの直下のサブフォルダ」)
$level1Dirs = Get-ChildItem -Path $resolvedBasePath -Directory
$targetOldDirs = @()

foreach ($dir in $level1Dirs) {
	if ($dir.Name -eq "(old)") { continue } # ベース直下が(old)の場合は2階層下ではないため除外
    
	# サブフォルダ内にある(old)ディレクトリを取得
	$oldDir = Get-ChildItem -Path $dir.FullName -Directory -Filter "(old)" -ErrorAction SilentlyContinue
	if ($oldDir) {
		$targetOldDirs += $oldDir
	}
}

if ($targetOldDirs.Count -eq 0) {
	Write-Host "処理対象となる 2階層下の (old) フォルダが見つかりませんでした。" -ForegroundColor Yellow
	Read-Host "`nEnterキーを押して終了します"
	return
}

$processedCount = 0
$skippedCount = 0
$errorCount = 0

foreach ($oldDir in $targetOldDirs) {
	Write-Host "`nフォルダをチェック中: $($oldDir.FullName)" -ForegroundColor Green

	# .aep ファイルを取得し、名前ルールでフィルタリング
	$aepFiles = Get-ChildItem -Path $oldDir.FullName -Filter "*.aep" -File | Where-Object {
		$_.Name -like "*_[tk]??.aep"
	}

	if ($aepFiles.Count -eq 0) {
		Write-Host "  -> 条件に合致する対象の .aep ファイルは見つかりませんでした。" -ForegroundColor DarkGray
		continue
	}

	foreach ($file in $aepFiles) {
		$baseName = $file.BaseName
		$ext = $file.Extension
        
		# 更新日時(LastWriteTime)を yyMMddHHmm 形式で取得
		$lastWriteStr = $file.LastWriteTime.ToString("yyMMddHHmm")
        
		# 新しいファイル名: [元のファイル名]_R[更新日時].aep
		$newName = "${baseName}_R${lastWriteStr}${ext}"
		$newFilePath = Join-Path -Path $oldDir.FullName -ChildPath $newName

		# 同名ファイルが既に存在する場合はスキップ
		if (Test-Path -Path $newFilePath) {
			Write-Host "  [スキップ] $newName は既に存在するため変更しません。(元ファイル: $($file.Name))" -ForegroundColor Yellow
			$skippedCount++
			continue
		}

		# ShouldProcess は -WhatIf 指定時に自動的に確認メッセージを出力し、実際の処理をブロックする
		if ($PSCmdlet.ShouldProcess($file.FullName, "ファイル名変更: $newName")) {
			try {
				Rename-Item -Path $file.FullName -NewName $newName -ErrorAction Stop
				Write-Host "  [成功] $($file.Name) -> $newName" -ForegroundColor Cyan
				$processedCount++
			}
			catch {
				
				Write-Host "  [エラー] $($file.Name) のリネームに失敗しました: $($_.Exception.Message)" -ForegroundColor Red
				$errorCount++
			}
		}
		else {
			# -WhatIf が指定されている場合、ShouldProcess は $false を返しここに入る
			# ShouldProcess自体が「What if: ...」を出力するが、ユーザーフレンドリーな独自メッセージも表示する
			Write-Host "  [予定] $($file.Name) -> $newName" -ForegroundColor Magenta
			$processedCount++
		}
	}
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "処理完了" -ForegroundColor Cyan
Write-Host "対象フォルダ数: $($targetOldDirs.Count)"
Write-Host "処理(予定)数  : $processedCount ファイル"
Write-Host "スキップ数    : $skippedCount ファイル"
Write-Host "エラー数      : $errorCount ファイル"
Write-Host "==========================================" -ForegroundColor Cyan

Read-Host "`nEnterキーを押して終了します"
