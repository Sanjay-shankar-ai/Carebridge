$app = New-Object -ComObject PowerPoint.Application
Write-Host "PowerPoint Application COM created successfully!"
$app.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($app) | Out-Null
