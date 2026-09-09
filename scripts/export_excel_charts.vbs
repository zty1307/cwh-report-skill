Option Explicit

Dim workbookPath, outputDir, trendSheetIndex, topicSheetIndex
Dim excel, workbook, sheet, chartObject, targetPath, sheetIndex

workbookPath = WScript.Arguments(0)
outputDir = WScript.Arguments(1)
trendSheetIndex = CInt(WScript.Arguments(2))
topicSheetIndex = CInt(WScript.Arguments(3))

Set excel = CreateObject("Excel.Application")
excel.Visible = False
excel.DisplayAlerts = False
excel.AutomationSecurity = 3

On Error Resume Next
Set workbook = excel.Workbooks.Open(workbookPath, 0, True)
If Err.Number <> 0 Then
  WScript.Echo "OPEN_ERROR " & Err.Number & " " & Err.Description
  excel.Quit
  WScript.Quit 2
End If

For Each sheetIndex In Array(trendSheetIndex, topicSheetIndex)
  Set sheet = workbook.Worksheets(CInt(sheetIndex))
  If CInt(sheetIndex) = trendSheetIndex Then
    targetPath = outputDir & "\trend_distribution_system.png"
  Else
    targetPath = outputDir & "\topic_distribution_system.png"
  End If
  If sheet.ChartObjects.Count > 0 Then
    Set chartObject = sheet.ChartObjects(1)
    Err.Clear
    chartObject.Chart.Export targetPath, "PNG"
    If Err.Number = 0 Then
      WScript.Echo CStr(sheetIndex) & "=" & targetPath
    Else
      WScript.Echo "EXPORT_ERROR " & CStr(sheetIndex) & " " & Err.Number & " " & Err.Description
    End If
  Else
    WScript.Echo "NO_CHART " & CStr(sheetIndex)
  End If
Next

workbook.Close False
excel.Quit
Set workbook = Nothing
Set excel = Nothing
