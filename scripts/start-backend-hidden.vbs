' Startet das Karaoke-Backend ohne sichtbares Fenster.
' Wird von scripts\backend-service.ps1 (install-startup) in den Autostart-Ordner
' verknuepft und laeuft dann bei jeder Anmeldung. Kein Admin noetig.
' Pfad wird relativ zum Skript aufgeloest (…\scripts\ -> Repo-Wurzel).

Dim fso, shell, scriptDir, repoRoot, backendDir, jar, logFile, javaExe, cmd
Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir  = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot   = fso.GetParentFolderName(scriptDir)
backendDir = fso.BuildPath(repoRoot, "backend")
jar        = fso.BuildPath(repoRoot, "deploy\karaoke-app.jar")
logFile    = fso.BuildPath(repoRoot, "deploy\logs\backend.log")

' Java finden: JAVA_HOME, sonst PATH
javaExe = shell.ExpandEnvironmentStrings("%JAVA_HOME%")
If javaExe <> "%JAVA_HOME%" And fso.FileExists(javaExe & "\bin\java.exe") Then
  javaExe = javaExe & "\bin\java.exe"
Else
  javaExe = "java.exe"
End If

If Not fso.FileExists(jar) Then
  WScript.Quit 1
End If

shell.CurrentDirectory = backendDir
cmd = """" & javaExe & """" & _
      " -XX:MaxRAMPercentage=75" & _
      " -Dlogging.file.name=""" & logFile & """" & _
      " -Dlogging.logback.rollingpolicy.max-file-size=10MB" & _
      " -Dlogging.logback.rollingpolicy.max-history=7" & _
      " -jar """ & jar & """"

' 0 = verstecktes Fenster, False = nicht auf Ende warten
shell.Run cmd, 0, False
