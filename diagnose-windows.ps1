# Kiosk Launcher Windows diagnostic
# Run as a standard user from a PowerShell window:
#   powershell -ExecutionPolicy Bypass -File diagnose-windows.ps1
# Writes C:\Kiosk\kiosk-diagnose.txt

$ErrorActionPreference = "SilentlyContinue"
$out = "C:\Kiosk\kiosk-diagnose.txt"
$lines = @()

function L($s) { $script:lines += [string]$s }

L "Kiosk Launcher Windows diagnostic"
L "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

L ""
L "== OS =="
$os = Get-CimInstance Win32_OperatingSystem
L "OS: $($os.Caption) $($os.Version) build $($os.BuildNumber)"
L "Arch: $env:PROCESSOR_ARCHITECTURE"
L "Computer: $env:COMPUTERNAME"

L ""
L "== Visual C++ runtime DLLs (System32) =="
foreach ($d in "vcruntime140.dll","msvcp140.dll","vcruntime140_1.dll","concrt140.dll") {
    $p = Join-Path $env:SystemRoot "System32\$d"
    L "$d : $(Test-Path $p)"
}

L ""
L "== Kiosk files =="
L "Kiosk.exe exists: $(Test-Path 'C:\Kiosk\Kiosk.exe')"
if (Test-Path 'C:\Kiosk\Kiosk.exe') {
    $f = Get-Item 'C:\Kiosk\Kiosk.exe'
    L "Kiosk.exe size: $($f.Length) bytes, modified: $($f.LastWriteTime)"
}
L "qwindows.dll (Qt platform plugin) under C:\Kiosk:"
Get-ChildItem -Path 'C:\Kiosk' -Recurse -Filter 'qwindows.dll' -ErrorAction SilentlyContinue |
    ForEach-Object { L "  $($_.FullName)" }

L ""
L "== kiosk-error.log =="
if (Test-Path 'C:\Kiosk\kiosk-error.log') {
    L (Get-Content 'C:\Kiosk\kiosk-error.log' -Raw)
} else {
    L "(no kiosk-error.log)"
}

L ""
L "== kiosk-diagnose.log =="
if (Test-Path 'C:\Kiosk\kiosk-diagnose.log') {
    L (Get-Content 'C:\Kiosk\kiosk-diagnose.log' -Raw)
} else {
    L "(no kiosk-diagnose.log — run Kiosk.exe --diagnose first)"
}

L ""
L "== Graphics =="
Get-CimInstance Win32_VideoController | ForEach-Object {
    L "GPU: $($_.Name)  driver: $($_.DriverVersion)"
}

L ""
L "== Recent Application-log errors mentioning Kiosk =="
$ev = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=1,2} -MaxEvents 100 |
    Where-Object { $_.Message -match 'Kiosk' }
if ($ev) {
    $ev | Select-Object -First 20 | ForEach-Object {
        L "[$($_.TimeCreated)] $($_.Id): $($_.Message)"
    }
} else {
    L "(none found)"
}

$lines | Out-File -FilePath $out -Encoding utf8
Write-Host "Diagnostic written to $out"
