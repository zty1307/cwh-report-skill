param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$Documents,
    [Parameter(Mandatory = $true)]
    [string]$Output
)

$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$all = @()

try {
    foreach ($path in $Documents) {
        $document = $word.Documents.Open($path, $false, $true)
        $rows = @()
        try {
            for ($index = 1; $index -le $document.Paragraphs.Count; $index++) {
                $paragraph = $document.Paragraphs.Item($index)
                $text = ($paragraph.Range.Text -replace "[\r\a]", "").Trim()
                if (-not $text) {
                    continue
                }
                if ($index -ne 1 -and $text.Length -gt 45) {
                    continue
                }
                $textRange = $paragraph.Range.Duplicate
                if ($textRange.End -gt $textRange.Start) {
                    $null = $textRange.MoveEnd(1, -1)
                }
                $rows += [ordered]@{
                    index = $index
                    text = $text.Substring(0, [Math]::Min(100, $text.Length))
                    style = $paragraph.Style.NameLocal
                    font_east_asia = $textRange.Font.NameFarEast
                    font_ascii = $textRange.Font.Name
                    size = $textRange.Font.Size
                    bold = $textRange.Font.Bold
                    alignment = $paragraph.Format.Alignment
                    first_line_indent = $paragraph.Format.FirstLineIndent
                    space_before = $paragraph.Format.SpaceBefore
                    space_after = $paragraph.Format.SpaceAfter
                    line_spacing = $paragraph.Format.LineSpacing
                }
            }
        }
        finally {
            $document.Close($false)
            $null = [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
        }
        $all += [ordered]@{ path = $path; paragraphs = $rows }
    }
}
finally {
    $word.Quit()
    $null = [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}

$json = $all | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($Output, $json, [System.Text.UTF8Encoding]::new($false))
$json
