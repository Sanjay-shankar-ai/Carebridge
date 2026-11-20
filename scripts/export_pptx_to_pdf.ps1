Param(
    [string]$pptxPath = "C:\CareBridge\AiMavericks_CareBridge_Submission.pptx",
    [string]$pdfPath = "C:\CareBridge\AiMavericks_CareBridge_Submission.pdf"
)

$pptxFull = [System.IO.Path]::GetFullPath($pptxPath)
$pdfFull = [System.IO.Path]::GetFullPath($pdfPath)

Write-Host "Exporting PPTX to PDF using native Microsoft PowerPoint..."
Write-Host "Input PPTX:  $pptxFull"
Write-Host "Output PDF: $pdfFull"

$pptApp = New-Object -ComObject PowerPoint.Application
try {
    # 32 = ppSaveAsPDF
    # Open presentation hidden / read-only
    $pres = $pptApp.Presentations.Open($pptxFull, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    $pres.SaveAs($pdfFull, 32)
    $pres.Close()
    Write-Host "PDF export completed successfully!"
}
catch {
    Write-Error "Error during PowerPoint PDF export: $_"
    exit 1
}
finally {
    $pptApp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pptApp) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
