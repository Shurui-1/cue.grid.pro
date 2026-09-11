Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
PythonW = ScriptDir & "\.venv\Scripts\pythonw.exe"
StartPy  = ScriptDir & "\start.py"
ExePath = ScriptDir & "\dist\CueGridPro\CueGridPro.exe"
WshShell.CurrentDirectory = ScriptDir

If FSO.FileExists(PythonW) And FSO.FileExists(StartPy) Then
    WshShell.Run Chr(34) & PythonW & Chr(34) & " " & Chr(34) & StartPy & Chr(34), 0, False
ElseIf FSO.FileExists(ExePath) Then
    WshShell.Run Chr(34) & ExePath & Chr(34), 0, False
Else
    WshShell.Run "pythonw.exe " & Chr(34) & StartPy & Chr(34), 0, False
End If
