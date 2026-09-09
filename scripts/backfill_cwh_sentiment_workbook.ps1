param(
    [Parameter(Mandatory = $true)][string]$BaseWorkbook,
    [Parameter(Mandatory = $true)][string]$SentimentSummary,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$Verification
)

$ErrorActionPreference = 'Stop'
$base = (Resolve-Path -LiteralPath $BaseWorkbook).Path
$summaryPath = (Resolve-Path -LiteralPath $SentimentSummary).Path
$outputPath = [IO.Path]::GetFullPath($Output)
$verificationPath = [IO.Path]::GetFullPath($Verification)
$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ready = @($summary.topics | Where-Object { $_.status -eq 'ready' -and [double]$_.denominator -gt 0 })
if ($summary.status -eq 'blocked_invalid_results') {
    throw 'Sentiment result gate failed; workbook backfill is blocked.'
}
if ($ready.Count -eq 0) {
    throw 'No topic has a valid sentiment denominator; no backfilled workbook will be created.'
}

New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($verificationPath)) | Out-Null
Copy-Item -LiteralPath $base -Destination $outputPath -Force

function Geometry {
    param($ChartObject)
    return @([double]$ChartObject.Left, [double]$ChartObject.Top, [double]$ChartObject.Width, [double]$ChartObject.Height)
}

$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.AskToUpdateLinks = $false
    $book = $excel.Workbooks.Open($outputPath, 0, $false)
    $totalSheet = $book.Worksheets.Item(2)
    $summarySheet = $book.Worksheets.Item($book.Worksheets.Count - 3)
    $totalGeometryBefore = Geometry $totalSheet.ChartObjects(1)
    $summaryGeometryBefore = Geometry $summarySheet.ChartObjects(1)
    $written = @()

    foreach ($topic in $ready) {
        $index = [int]$topic.index
        $row = $index + 3
        if ($index -lt 1 -or $row -gt $summarySheet.UsedRange.Rows.Count) {
            throw "Invalid topic index: $index"
        }
        $positive = [double]$topic.positive
        $neutral = [double]$topic.neutral
        $negative = [double]$topic.negative
        $sum = $positive + $neutral + $negative
        if ([Math]::Abs($sum - 1.0) -gt 0.000001) {
            throw "Topic $index sentiment percentages do not sum to 1."
        }
        $formatSource = $summarySheet.Cells.Item($row, 8)
        $target = $summarySheet.Range("G$row:I$row")
        $formatSource.Copy()
        $target.PasteSpecial(-4122)
        $summarySheet.Cells.Item($row, 7).Value2 = $positive
        $summarySheet.Cells.Item($row, 8).Value2 = $neutral
        $summarySheet.Cells.Item($row, 9).Value2 = $negative
        # PowerShell COM may apply a scalar NumberFormat assignment only to
        # the first cell of a multi-cell Range.  Set each cell explicitly so
        # zero values also display as percentages in all three columns.
        foreach ($column in 7..9) {
            $summarySheet.Cells.Item($row, $column).NumberFormat = '0.0%'
        }
        $written += [ordered]@{
            index = $index
            row = $row
            denominator = [int]$topic.denominator
            positive = $positive
            neutral = $neutral
            negative = $negative
        }
    }
    # Do not assign CutCopyMode here: recent Office COM interop exposes only
    # xlCopy/xlCut as valid enum members and rejects both Boolean false and 0.
    $excel.CalculateFull()
    $book.Save()
    $totalGeometryAfter = Geometry $totalSheet.ChartObjects(1)
    $summaryGeometryAfter = Geometry $summarySheet.ChartObjects(1)
    if (($totalGeometryBefore -join '|') -ne ($totalGeometryAfter -join '|') -or ($summaryGeometryBefore -join '|') -ne ($summaryGeometryAfter -join '|')) {
        throw 'Chart geometry changed during sentiment backfill.'
    }
    $result = [ordered]@{
        status = 'ok'
        base_workbook = $base
        output = $outputPath
        written_topics = $written
        total_chart_geometry_preserved = $true
        summary_chart_geometry_preserved = $true
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $verificationPath -Encoding UTF8
    $book.Close($true)
    $book = $null
}
finally {
    if ($book) {
        try { $book.Close($false) } catch {}
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book) } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel) } catch {}
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
