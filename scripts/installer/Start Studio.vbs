Option Explicit

Dim shell, files, root, scriptPath, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
scriptPath = root & "\App\KodKon Studio\scripts\start-desktop.ps1"
command = "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptPath & """ -InstallRoot """ & root & """"
shell.Run command, 0, False
