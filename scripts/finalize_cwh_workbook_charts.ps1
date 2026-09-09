param(
    [Parameter(Mandatory = $true)][string]$Workbook,
    [Parameter(Mandatory = $true)][string]$Verification,
    [Parameter(Mandatory = $true)][string]$PreviewDir
)

$ErrorActionPreference = 'Stop'
$xlLineMarkers = 65
$xlBarClustered = 57
$xlLegendPositionBottom = -4107
$xlMove = 2

function Nice-Step {
    param([double]$Maximum, [int]$Intervals = 5)
    if ($Maximum -le 0) { return 1.0 }
    $raw = $Maximum / $Intervals
    $power = [Math]::Pow(10, [Math]::Floor([Math]::Log10($raw)))
    $fraction = $raw / $power
    if ($fraction -le 1) { $nice = 1 }
    elseif ($fraction -le 2) { $nice = 2 }
    elseif ($fraction -le 3) { $nice = 3 }
    elseif ($fraction -le 5) { $nice = 5 }
    else { $nice = 10 }
    return [double]($nice * $power)
}

function Quote-Sheet {
    param([string]$Name)
    return "'" + $Name.Replace("'", "''") + "'"
}

function Chart-Geometry {
    param($ChartObject)
    return [ordered]@{
        left = [double]$ChartObject.Left
        top = [double]$ChartObject.Top
        width = [double]$ChartObject.Width
        height = [double]$ChartObject.Height
        top_left_cell = $ChartObject.TopLeftCell.Address()
        bottom_right_cell = $ChartObject.BottomRightCell.Address()
    }
}

$source = (Resolve-Path -LiteralPath $Workbook).Path
$verificationPath = [IO.Path]::GetFullPath($Verification)
$previewPath = [IO.Path]::GetFullPath($PreviewDir)
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($verificationPath)) | Out-Null
New-Item -ItemType Directory -Force -Path $previewPath | Out-Null

$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.AskToUpdateLinks = $false
    $book = $excel.Workbooks.Open($source, 0, $false)

    $totalSheet = $book.Worksheets.Item(2)
    $summarySheet = $book.Worksheets.Item($book.Worksheets.Count - 3)
    if ($totalSheet.ChartObjects().Count -ne 1 -or $summarySheet.ChartObjects().Count -ne 1) {
        throw 'Expected exactly one chart on the total sheet and one on the summary sheet.'
    }

    $gutterWidths = @(10.5625, 13, 10.9375, 15.8125, 10.9375, 22.4375)
    for ($offset = 0; $offset -lt $gutterWidths.Count; $offset++) {
        $column = $totalSheet.Columns.Item(9 + $offset)
        if ([Math]::Abs([double]$column.ColumnWidth - [double]$gutterWidths[$offset]) -gt 0.01) {
            # Excel COM reports imported column widths 0.5625 above the setter
            # value on this template. Compensate only when the builder output
            # is not already at the accepted width.
            $column.ColumnWidth = [double]$gutterWidths[$offset] - 0.5625
        }
    }

    $totalLastRow = 4
    while ($totalSheet.Cells.Item($totalLastRow + 1, 1).Value2 -ne $null -and $totalLastRow -lt 1000) {
        $totalLastRow++
    }
    $maximumTotal = 0.0
    $sumTotal = 0.0
    for ($row = 4; $row -le $totalLastRow; $row++) {
        $value = [double]$totalSheet.Cells.Item($row, 8).Value2
        if ($value -gt $maximumTotal) { $maximumTotal = $value }
        $sumTotal += $value
    }
    $totalObject = $totalSheet.ChartObjects(1)
    $totalChart = $totalObject.Chart
    $totalChart.ChartType = $xlLineMarkers
    $totalChart.ChartStyle = 2
    while ($totalChart.SeriesCollection().Count -gt 0) {
        $totalChart.SeriesCollection(1).Delete()
    }
    $totalSeries = $totalChart.SeriesCollection().NewSeries()
    $totalSeries.Name = [string]$totalSheet.Cells.Item(3, 8).Value2
    $totalSeries.XValues = $totalSheet.Range("A4:A$totalLastRow")
    $totalSeries.Values = $totalSheet.Range("H4:H$totalLastRow")
    $totalChart.HasTitle = $true
    $titleLabel = ([string]$totalSeries.Name).Replace(
        ([char]0x91cf).ToString(),
        ([char]0x603b).ToString() + ([char]0x91cf).ToString()
    )
    $titleText = $titleLabel + ([char]0xFF1A).ToString() + ' ' + (($sumTotal / 10000).ToString('0.0')) + ([char]0x4E07).ToString() + ([char]0x6761).ToString()
    $totalChart.ChartTitle.Text = $titleText
    $totalChart.ChartTitle.Format.TextFrame2.TextRange.Font.Name = 'Microsoft YaHei'
    $totalChart.ChartTitle.Format.TextFrame2.TextRange.Font.Size = 18
    $totalChart.ChartTitle.Format.TextFrame2.TextRange.Font.Bold = -1
    $totalChart.HasLegend = $true
    $totalChart.Legend.Position = $xlLegendPositionBottom
    $totalChart.ChartGroups(1).VaryByCategories = $false
    $totalSeries.MarkerStyle = 8
    $totalSeries.MarkerSize = 5
    $totalSeries.Smooth = $false
    $totalSeries.Format.Line.ForeColor.RGB = 6697728
    $totalSeries.Format.Line.Weight = 1
    $totalSeries.MarkerBackgroundColor = 16777215
    $totalSeries.MarkerForegroundColor = 6697728
    $totalSeries.ApplyDataLabels()
    $peakIndex = 1
    $peakValue = -1.0
    for ($pointIndex = 1; $pointIndex -le $totalSeries.Points().Count; $pointIndex++) {
        $pointValue = [double]$totalSheet.Cells.Item($pointIndex + 3, 8).Value2
        $point = $totalSeries.Points($pointIndex)
        $point.DataLabel.NumberFormat = ';;;'
        if ($pointValue -gt $peakValue) {
            $peakValue = $pointValue
            $peakIndex = $pointIndex
        }
    }
    $totalSeries.Points($peakIndex).DataLabel.NumberFormat = '0'
    $totalSeries.Points($peakIndex).DataLabel.Position = 0
    $totalObject.Left = [double]$totalSheet.Cells.Item(2, 9).Left + 27.48828125
    $totalObject.Top = 24.098503112792969
    $totalObject.Width = 411.02362060546875
    $totalObject.Height = 255
    $totalObject.Placement = $xlMove

    $totalStep = Nice-Step $maximumTotal 5
    $totalMaximum = [Math]::Ceiling($maximumTotal / $totalStep) * $totalStep
    $totalCategoryAxis = $totalChart.Axes(1, 1)
    $totalCategoryAxis.TickLabels.NumberFormat = 'm/d;@'
    $totalCategoryAxis.TickLabels.Font.Name = 'Microsoft YaHei'
    $totalCategoryAxis.TickLabels.Font.Size = 10
    $totalCategoryAxis.HasMajorGridlines = $false
    $totalCategoryAxis.Format.Line.Visible = 0
    $totalValueAxis = $totalChart.Axes(2, 1)
    $totalValueAxis.MinimumScale = 0
    $totalValueAxis.MaximumScale = $totalMaximum
    $totalValueAxis.MajorUnit = $totalStep
    $totalValueAxis.TickLabels.NumberFormat = 'General'
    $totalValueAxis.TickLabels.Font.Name = 'Microsoft YaHei'
    $totalValueAxis.TickLabels.Font.Size = 10
    $totalValueAxis.HasMajorGridlines = $true
    $totalValueAxis.MajorGridlines.Format.Line.ForeColor.RGB = 12763842
    $totalValueAxis.MajorGridlines.Format.Line.Weight = 0.25
    $totalValueAxis.Format.Line.Visible = 0

    $childCount = 0
    for ($row = 4; $row -lt 1000; $row++) {
        if ($summarySheet.Cells.Item($row, 1).Value2 -is [double] -or $summarySheet.Cells.Item($row, 1).Value2 -is [int]) {
            $childCount++
        } else { break }
    }
    if ($childCount -lt 1) { throw 'No child rows found on the summary sheet.' }
    $helperLastRow = 19 + $childCount
    $summaryObject = $summarySheet.ChartObjects(1)
    $summaryChart = $summaryObject.Chart
    $summaryChart.ChartType = $xlBarClustered
    $summaryChart.ChartStyle = 2
    while ($summaryChart.SeriesCollection().Count -gt 0) {
        $summaryChart.SeriesCollection(1).Delete()
    }
    $summarySeries = $summaryChart.SeriesCollection().NewSeries()
    $summaryChart.HasTitle = $false
    $summaryChart.HasLegend = $false
    $labels = New-Object object[] $childCount
    $longestIndex = 0
    for ($labelIndex = 0; $labelIndex -lt $childCount; $labelIndex++) {
        $labels[$labelIndex] = [string]$summarySheet.Cells.Item(20 + $labelIndex, 2).Value2
        if ($labels[$labelIndex].Length -gt $labels[$longestIndex].Length) { $longestIndex = $labelIndex }
    }
    if ($labels[$longestIndex].Length -gt 4) {
        $labels[$longestIndex] = $labels[$longestIndex].Substring(0, 4) + "`n" + $labels[$longestIndex].Substring(4)
    }
    $summarySeries.XValues = $labels
    $summarySeries.Values = $summarySheet.Range("C20:C$helperLastRow")
    $summarySeries.Format.Fill.ForeColor.RGB = 6697728
    $summarySeries.ApplyDataLabels()
    $tenThousandFormatSuffix = '"' + ([char]0x4E07).ToString() + '"'
    $summarySeries.DataLabels().NumberFormatLinked = $false
    for ($pointIndex = 1; $pointIndex -le $summarySeries.Points().Count; $pointIndex++) {
        $value = [double]$summarySheet.Cells.Item($pointIndex + 19, 3).Value2
        $point = $summarySeries.Points($pointIndex)
        $point.DataLabel.NumberFormatLinked = $false
        if ([Math]::Abs($value - [Math]::Round($value, 0)) -lt 0.0000001) {
            $point.DataLabel.NumberFormat = '0' + $tenThousandFormatSuffix
        }
        else {
            $point.DataLabel.NumberFormat = '0.0' + $tenThousandFormatSuffix
        }
        $point.DataLabel.Position = 2
        $point.DataLabel.Font.Name = 'Microsoft YaHei'
        $point.DataLabel.Font.Size = 10
    }
    $summarySheet.Range("Z20:Z$helperLastRow").ClearContents()
    $summarySheet.Columns.Item(26).Hidden = $false
    $summaryObject.Left = 487.62503051757813
    $summaryObject.Top = 330.5
    $summaryObject.Width = 411.02362060546875
    $summaryObject.Height = 261.47503662109375
    $summaryObject.Placement = $xlMove

    $maximumSummary = 0.0
    for ($row = 20; $row -le $helperLastRow; $row++) {
        $value = [double]$summarySheet.Cells.Item($row, 3).Value2
        if ($value -gt $maximumSummary) { $maximumSummary = $value }
    }
    $summaryStep = [Math]::Ceiling(($maximumSummary / 4) * 10) / 10
    if ($summaryStep -le 0) { $summaryStep = 0.1 }
    $summaryCategoryAxis = $summaryChart.Axes(1, 1)
    $summaryCategoryAxis.TickLabels.NumberFormat = '@'
    $summaryCategoryAxis.TickLabels.Font.Name = 'Microsoft YaHei'
    $summaryCategoryAxis.TickLabels.Font.Size = 10
    $summaryCategoryAxis.HasMajorGridlines = $false
    $summaryCategoryAxis.MajorTickMark = 3
    $summaryCategoryAxis.Format.Line.Visible = -1
    $summaryValueAxis = $summaryChart.Axes(2, 1)
    $summaryValueAxis.MinimumScale = 0
    $summaryValueAxis.MaximumScale = $summaryStep * 5
    $summaryValueAxis.MajorUnit = $summaryStep
    $summaryValueAxis.TickLabels.NumberFormat = '0.0'
    $summaryValueAxis.TickLabels.Font.Name = 'Microsoft YaHei'
    $summaryValueAxis.TickLabels.Font.Size = 10
    $summaryValueAxis.HasMajorGridlines = $false
    $summaryValueAxis.TickLabelPosition = -4142
    $summaryValueAxis.MajorTickMark = -4142
    $summaryValueAxis.Format.Line.Visible = 0

    $excel.CalculateFull()
    # Refreshing after chart customization makes Excel rebuild parts of the
    # chart from the source range and can discard the custom title/data labels.
    # Save the fully configured chart state without refreshing it.
    $book.Save()
    $previewExported = $true
    try {
        [void]$totalChart.Export((Join-Path $previewPath 'total_chart_final.png'), 'PNG')
        [void]$summaryChart.Export((Join-Path $previewPath 'summary_chart_final.png'), 'PNG')
    }
    catch {
        # Chart export can be unavailable in non-interactive Excel sessions.
        # The workbook itself has already been saved and remains the authority.
        $previewExported = $false
    }

    $result = [ordered]@{
        status = 'ok'
        workbook = $source
        total_chart = Chart-Geometry $totalObject
        total_axis = [ordered]@{ maximum = $totalMaximum; major_unit = $totalStep }
        summary_chart = Chart-Geometry $summaryObject
        summary_axis = [ordered]@{ maximum = $summaryStep * 5; major_unit = $summaryStep }
        sentiment_cells_blank = ($excel.WorksheetFunction.CountA($summarySheet.Range("G4:I$($childCount + 3)")) -eq 0)
        preview_exported = $previewExported
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $verificationPath -Encoding UTF8
    $book.Close($false)
    $book = $null
}
catch {
    throw "Chart finalization failed at line $($_.InvocationInfo.ScriptLineNumber): $($_.Exception.Message)"
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
