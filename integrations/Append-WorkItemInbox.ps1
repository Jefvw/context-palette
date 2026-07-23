$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Resolve-WorkbookPath {
    param(
        [string]$PathText
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return $null
    }
    try {
        return [System.IO.Path]::GetFullPath($PathText)
    }
    catch {
        return $null
    }
}

$excel = $null
$workbook = $null
$sheet = $null
$openedWorkbook = $false
$createdExcel = $false
$createdSheet = $false
$createdHeaders = $false
$row = 0
$writeStarted = $false
$saved = $false

try {
    $rawRequest = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($rawRequest) -or $rawRequest.Length -gt 200000) {
        throw "The Inbox request is empty or too large."
    }
    $request = $rawRequest | ConvertFrom-Json
    $workbookPath = Resolve-WorkbookPath([string]$request.workbook)
    if (
        [string]::IsNullOrWhiteSpace($workbookPath) -or
        -not [System.IO.Path]::IsPathRooted($workbookPath) -or
        [System.IO.Path]::GetExtension($workbookPath).ToLowerInvariant() -ne ".xlsx" -or
        -not (Test-Path -LiteralPath $workbookPath -PathType Leaf)
    ) {
        throw "The matching .xlsx workbook is unavailable."
    }

    try {
        $excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
    }
    catch {
        $excel = New-Object -ComObject Excel.Application
        $createdExcel = $true
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $excel.AutomationSecurity = 3
    }

    foreach ($candidate in $excel.Workbooks) {
        $candidatePath = Resolve-WorkbookPath([string]$candidate.FullName)
        if ([string]::IsNullOrWhiteSpace($candidatePath)) {
            continue
        }
        if ([string]::Equals(
            $candidatePath,
            $workbookPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            $workbook = $candidate
            break
        }
    }
    if ($null -eq $workbook) {
        $workbook = $excel.Workbooks.Open($workbookPath, 0, $false)
        $openedWorkbook = $true
    }
    if ($workbook.ReadOnly) {
        throw "The matching workbook is read-only or locked by another application."
    }

    try {
        $sheet = $workbook.Worksheets.Item("Inbox")
    }
    catch {
        $sheet = $workbook.Worksheets.Add()
        $sheet.Name = "Inbox"
        $createdSheet = $true
    }

    $isEmpty = $true
    for ($column = 1; $column -le 4; $column++) {
        if (-not [string]::IsNullOrEmpty([string]$sheet.Cells.Item(1, $column).Value2)) {
            $isEmpty = $false
            break
        }
    }
    if ($isEmpty) {
        $createdHeaders = $true
        $headers = @("Added", "Text", "Link", "Source")
        for ($column = 1; $column -le 4; $column++) {
            $headerCell = $sheet.Cells.Item(1, $column)
            $headerCell.NumberFormat = "@"
            $headerCell.Value2 = $headers[$column - 1]
            $headerCell.Font.Bold = $true
        }
    }

    $lastRow = 1
    for ($column = 1; $column -le 4; $column++) {
        $columnLastRow = $sheet.Cells.Item($sheet.Rows.Count, $column).End(-4162).Row
        if ($columnLastRow -gt $lastRow) {
            $lastRow = $columnLastRow
        }
    }
    $row = $lastRow + 1
    $writeStarted = $true

    $addedCell = $sheet.Cells.Item($row, 1)
    $addedCell.NumberFormat = "@"
    $addedCell.Value2 = [string]$request.added

    $textCell = $sheet.Cells.Item($row, 2)
    $textCell.NumberFormat = "@"
    $textCell.Value2 = [string]$request.text

    $link = [string]$request.link
    $linkCell = $sheet.Cells.Item($row, 3)
    $linkCell.NumberFormat = "@"
    if (-not [string]::IsNullOrWhiteSpace($link)) {
        [void]$sheet.Hyperlinks.Add($linkCell, $link, "", "", $link)
    }

    $sourceCell = $sheet.Cells.Item($row, 4)
    $sourceCell.NumberFormat = "@"
    $sourceCell.Value2 = [string]$request.source

    $workbook.Save()
    $saved = $true
    @{
        row = $row
        created_sheet = $createdSheet
    } | ConvertTo-Json -Compress
}
catch {
    if (
        ($writeStarted -or $createdHeaders -or $createdSheet) -and
        -not $saved -and
        $null -ne $sheet
    ) {
        try {
            if ($createdSheet) {
                $previousAlerts = $excel.DisplayAlerts
                $excel.DisplayAlerts = $false
                $sheet.Delete()
                $excel.DisplayAlerts = $previousAlerts
            }
            else {
                if ($row -gt 0) {
                    $sheet.Range("A$row", "D$row").Clear()
                }
                if ($createdHeaders) {
                    $sheet.Range("A1", "D1").Clear()
                }
            }
        }
        catch {}
    }
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($null -ne $workbook -and $openedWorkbook) {
        try { $workbook.Close($false) } catch {}
    }
    if ($null -ne $excel -and $createdExcel) {
        try { $excel.Quit() } catch {}
    }
    foreach ($comObject in @($sheet, $workbook, $excel)) {
        if ($null -ne $comObject) {
            try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($comObject) } catch {}
        }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
