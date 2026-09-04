<#
.SYNOPSIS
  Betreibt das Karaoke-Backend als 24/7-Dienst auf diesem Windows-Rechner
  (per Scheduled Task - kein Docker, kein Extra-Tool noetig).

.DESCRIPTION
  install   Jar nach deploy/ kopieren, Task anlegen + Firewall (TCP 8080) oeffnen, starten
  update    Neu bauen (mvnw), Jar aktualisieren, Backend neu starten
  allow-lan Nur die Firewall-Regel fuer den Heimnetz-Zugriff (braucht Admin)
  start / stop / restart / status / uninstall  wie erwartet

  Der Task laeuft mit Arbeitsverzeichnis backend/, damit die relativen Pfade aus
  application.properties (./data/karaoke-db, ../data/songs) auf die bestehenden
  Daten zeigen. Logs: deploy/logs/backend.log (rotiert, 7 Tage).

  Standard: Task laeuft nur, wenn der Benutzer angemeldet ist (kein Passwort
  noetig). Mit -RunWhenLoggedOff laeuft er per S4U auch ohne aktive Sitzung
  weiter (ueberlebt Abmelden/Sperrbildschirm; braucht keine Passwort-Eingabe,
  aber Task Scheduler kann beim ersten Mal nachfragen).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 install
  powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 update
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('install', 'update', 'start', 'stop', 'restart', 'status', 'uninstall',
    'install-startup', 'uninstall-startup', 'allow-lan')]
  [string]$Action = 'status',

  [switch]$RunWhenLoggedOff
)

$ErrorActionPreference = 'Stop'
$TaskName  = 'KaraokeBackend'
$FwRule    = 'Karaoke Backend (LAN 8080)'
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$DeployDir = Join-Path $RepoRoot 'deploy'
$LogDir    = Join-Path $DeployDir 'logs'
$Jar       = Join-Path $DeployDir 'karaoke-app.jar'
$LogFile   = Join-Path $LogDir 'backend.log'
$HealthUrl = 'http://localhost:8080/actuator/health'

function Find-Java {
  if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return "$env:JAVA_HOME\bin\java.exe" }
  $cmd = Get-Command java -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $found = Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Filter java.exe -Recurse -ErrorAction SilentlyContinue |
    Where-Object FullName -Match 'jdk-21' | Select-Object -First 1
  if ($found) { return $found.FullName }
  throw 'Kein Java 21 gefunden (JAVA_HOME setzen oder Temurin 21 installieren).'
}

function Build-Jar {
  Write-Host '-> mvnw clean package -DskipTests' -ForegroundColor Cyan
  Push-Location $BackendDir
  try {
    & (Join-Path $BackendDir 'mvnw.cmd') -q -B clean package -DskipTests
    if ($LASTEXITCODE -ne 0) { throw "Build fehlgeschlagen (exit $LASTEXITCODE)" }
  } finally { Pop-Location }
}

function Copy-Jar {
  $built = Get-ChildItem (Join-Path $BackendDir 'target') -Filter '*.jar' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notmatch 'sources|javadoc' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $built) { throw "Keine gebaute Jar in backend/target - erst 'update' oder 'mvnw package' laufen lassen." }
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  Copy-Item $built.FullName $Jar -Force
  Write-Host "Jar -> $Jar  ($([math]::Round($built.Length/1MB,1)) MB, $($built.LastWriteTime))" -ForegroundColor Green
}

function Register-Task {
  $java = Find-Java
  $argLine = @(
    '-XX:MaxRAMPercentage=75'
    "-Dlogging.file.name=$LogFile"
    '-Dlogging.logback.rollingpolicy.max-file-size=10MB'
    '-Dlogging.logback.rollingpolicy.max-history=7'
    '-jar', "`"$Jar`""
  ) -join ' '

  $action = New-ScheduledTaskAction -Execute $java -Argument $argLine -WorkingDirectory $BackendDir
  $triggers = @(
    New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    New-ScheduledTaskTrigger -AtStartup
  )
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

  if ($RunWhenLoggedOff) {
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
  } else {
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  }

  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal `
    -Description 'Karaoke-App Spring-Boot-Backend (24/7)' | Out-Null
  Write-Host "Scheduled Task '$TaskName' registriert (Java: $java)" -ForegroundColor Green
}

$StartupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'KaraokeBackend.lnk'
$VbsLauncher = Join-Path $PSScriptRoot 'start-backend-hidden.vbs'

function Install-StartupLauncher {
  # Kein Admin noetig: Verknuepfung im Autostart-Ordner -> startet bei Anmeldung.
  # Kein Auto-Neustart bei Absturz (dafuer 'install' als Scheduled Task, elevated).
  $sh = New-Object -ComObject WScript.Shell
  $lnk = $sh.CreateShortcut($StartupLnk)
  $lnk.TargetPath = "$env:SystemRoot\System32\wscript.exe"
  $lnk.Arguments = "`"$VbsLauncher`""
  $lnk.WorkingDirectory = $BackendDir
  $lnk.Description = 'Karaoke-App Backend (Autostart)'
  $lnk.Save()
  Write-Host "Autostart-Verknuepfung -> $StartupLnk" -ForegroundColor Green
}

function Start-ViaVbs {
  & "$env:SystemRoot\System32\wscript.exe" $VbsLauncher
  Write-Host 'Backend (versteckt) gestartet.' -ForegroundColor Green
}

function Stop-BackendProcess {
  $procs = Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -match 'karaoke-app\.jar' }
  foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  if ($procs) { Write-Host "gestoppt (PID $($procs.ProcessId -join ', '))." } else { Write-Host 'kein laufender Backend-Prozess.' }
}

function Add-FirewallRule {
  # Eingehend TCP 8080 im privaten Profil (Heimnetz) erlauben - sonst blockt
  # die Windows-Firewall den Zugriff vom Handy auf http://<pc-ip>:8080.
  if (Get-NetFirewallRule -DisplayName $FwRule -ErrorAction SilentlyContinue) {
    Write-Host "Firewall-Regel '$FwRule' existiert bereits."
    return
  }
  New-NetFirewallRule -DisplayName $FwRule -Direction Inbound -Protocol TCP `
    -LocalPort 8080 -Action Allow -Profile Private | Out-Null
  Write-Host "Firewall-Regel '$FwRule' angelegt (TCP 8080, privates Netz)." -ForegroundColor Green
}

function Remove-FirewallRule {
  Get-NetFirewallRule -DisplayName $FwRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}

function Wait-Health {
  Write-Host -NoNewline 'Warte auf /actuator/health '
  foreach ($i in 1..40) {
    try {
      $r = Invoke-RestMethod $HealthUrl -TimeoutSec 2
      if ($r.status -eq 'UP') { Write-Host " UP" -ForegroundColor Green; return $true }
    } catch { }
    Start-Sleep 1; Write-Host -NoNewline '.'
  }
  Write-Host " keine Antwort" -ForegroundColor Yellow
  Write-Host "letzte Logzeilen ($LogFile):"
  if (Test-Path $LogFile) { Get-Content $LogFile -Tail 20 }
  return $false
}

function Show-Status {
  $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($t) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Task '$TaskName': $($t.State)  LastRun=$($info.LastRunTime)  LastResult=$($info.LastTaskResult)"
  } else {
    Write-Host "Scheduled Task: nicht registriert" -ForegroundColor DarkGray
  }
  $port = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
  Write-Host ("Port 8080: " + $(if ($port) { "belegt (PID $($port[0].OwningProcess))" } else { "frei" }))
  try { $h = Invoke-RestMethod $HealthUrl -TimeoutSec 2; Write-Host "Health: $($h.status)" -ForegroundColor Green }
  catch { Write-Host "Health: nicht erreichbar" -ForegroundColor Yellow }
  $fw = Get-NetFirewallRule -DisplayName $FwRule -ErrorAction SilentlyContinue
  Write-Host ("Firewall (LAN 8080): " + $(if ($fw) { "offen" } else { "zu - 'allow-lan' (Admin) fuer Handy-Zugriff" }))
  $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254)' } | Select-Object -First 1).IPAddress
  if ($ip) { Write-Host "Song-Liste im Heimnetz: http://${ip}:8080/songs" }
}

$hasTask = { [bool](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) }

switch ($Action) {
  'install' {
    Copy-Jar
    $elevated = $false
    try {
      Register-Task
      Start-ScheduledTask -TaskName $TaskName
      $elevated = $true
    } catch {
      Write-Host "Scheduled Task nicht moeglich ($($_.Exception.Message))." -ForegroundColor Yellow
      Write-Host 'Fallback: Autostart-Verknuepfung (kein Admin, kein Auto-Neustart bei Absturz).' -ForegroundColor Yellow
      Write-Host "Fuer den vollen Dienst: PowerShell als Administrator -> scripts\backend-service.ps1 install" -ForegroundColor Yellow
      Install-StartupLauncher
      Stop-BackendProcess; Start-Sleep 1; Start-ViaVbs
    }
    try { Add-FirewallRule }
    catch {
      Write-Host "Firewall-Regel nicht moeglich ($($_.Exception.Message))." -ForegroundColor Yellow
      Write-Host "Fuer LAN-Zugriff (Handy -> http://<pc-ip>:8080): PowerShell als Administrator ->" -ForegroundColor Yellow
      Write-Host "  scripts\backend-service.ps1 allow-lan" -ForegroundColor Yellow
    }
    Wait-Health | Out-Null; Show-Status
  }
  'allow-lan' { Add-FirewallRule }
  'update' {
    Build-Jar; Copy-Jar
    if (& $hasTask) {
      Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
      Start-Sleep 2; Start-ScheduledTask -TaskName $TaskName
    } else {
      Stop-BackendProcess; Start-Sleep 1; Start-ViaVbs
    }
    Wait-Health | Out-Null; Show-Status
  }
  'start' {
    if (& $hasTask) { Start-ScheduledTask -TaskName $TaskName } else { Start-ViaVbs }
    Wait-Health | Out-Null
  }
  'stop' {
    if (& $hasTask) { Stop-ScheduledTask -TaskName $TaskName }
    Stop-BackendProcess
  }
  'restart' {
    if (& $hasTask) {
      Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Start-Sleep 2
      Start-ScheduledTask -TaskName $TaskName
    } else {
      Stop-BackendProcess; Start-Sleep 1; Start-ViaVbs
    }
    Wait-Health | Out-Null
  }
  'status' { Show-Status; if (Test-Path $StartupLnk) { Write-Host "Autostart-Verknuepfung: vorhanden" } }
  'uninstall' {
    if (& $hasTask) {
      Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
      Write-Host "Task '$TaskName' entfernt."
    }
    if (Test-Path $StartupLnk) { Remove-Item $StartupLnk -Force; Write-Host 'Autostart-Verknuepfung entfernt.' }
    try { Remove-FirewallRule } catch { }
    Stop-BackendProcess
    Write-Host '(deploy/ + Daten bleiben.)'
  }
  'install-startup'   { Copy-Jar; Install-StartupLauncher; Stop-BackendProcess; Start-Sleep 1; Start-ViaVbs; Wait-Health | Out-Null; Show-Status }
  'uninstall-startup' { if (Test-Path $StartupLnk) { Remove-Item $StartupLnk -Force }; Stop-BackendProcess; Write-Host 'Autostart entfernt, Backend gestoppt.' }
}
