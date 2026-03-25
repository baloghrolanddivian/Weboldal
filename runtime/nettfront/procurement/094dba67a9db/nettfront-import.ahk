; AutoHotkey v2.0+
#SingleInstance Force
Persistent

sleeptime := 300
doublesleeptime := 3000
csvPath := "C:\\Users\\baloghr\\Documents\\GitHub\\Weboldal\\runtime\\nettfront\\procurement\\094dba67a9db\\rendeles_sima.csv"
isRunning := false

Esc::
{
    ExitApp
}

+Space::
{
    global csvPath, sleeptime, doublesleeptime, isRunning
    if (isRunning)
        return
    isRunning := true

    try content := FileRead(csvPath, "UTF-8")
    catch {
        MsgBox "Hiba: Nem sikerult beolvasni a fajlt: " csvPath
        ExitApp
    }

    lines := StrSplit(content, "`n", "`r")
    for _, line in lines
    {
        line := Trim(line)
        if (line = "")
            continue
        if GetKeyState("Esc", "P")
            ExitApp

        parts := StrSplit(line, ";")
        if parts.Length < 2
            continue

        cikkszam := Trim(parts[1])
        mennyiseg := Trim(parts[2])
        if (cikkszam = "")
            continue

        A_Clipboard := cikkszam
        Send "{Insert}"
        Sleep doublesleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{Tab 2}"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "^v"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{Tab}"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        A_Clipboard := mennyiseg
        Send "^v"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{Tab}"
        Send "{Enter}"
        Sleep sleeptime
    }

    ExitApp
}
