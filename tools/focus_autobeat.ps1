Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class WindowFocus {
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
'@
$process = Get-Process -Name AutoBeat5 -ErrorAction Stop | Select-Object -First 1
[WindowFocus]::ShowWindowAsync($process.MainWindowHandle, 9) | Out-Null
Start-Sleep -Milliseconds 300
[WindowFocus]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
Write-Output "FOCUSED_PID=$($process.Id) HANDLE=$($process.MainWindowHandle)"
