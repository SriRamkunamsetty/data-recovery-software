$WshShell = New-Object -ComObject WScript.Shell

$p1 = "$env:USERPROFILE\OneDrive\Desktop"
$p2 = "$env:USERPROFILE\Desktop"

$desktops = @($p1, $p2)

foreach ($dp in $desktops) {
    if (Test-Path $dp) {
        $shortcutPath = Join-Path $dp "RecoverX.lnk"
        $shortcut = $WshShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = "D:\Projects\data recovery Software\dist\recoverx\recoverx.exe"
        $shortcut.Arguments = "gui"
        $shortcut.WorkingDirectory = "D:\Projects\data recovery Software"
        $shortcut.IconLocation = "D:\Projects\data recovery Software\assets\icon.ico,0"
        $shortcut.Description = "RecoverX - Forensic Removable Storage Data Recovery"
        $shortcut.Save()
        Write-Host "Created shortcut: $shortcutPath"
    }
}
