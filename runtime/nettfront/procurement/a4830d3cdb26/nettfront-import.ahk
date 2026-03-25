; AutoHotkey v2.0+
#SingleInstance Force
Persistent

sleeptime := 300
doublesleeptime := 3000
csvPath := "C:\\Users\\baloghr\\Documents\\GitHub\\Weboldal\\runtime\\nettfront\\procurement\\a4830d3cdb26\\rendeles_sima.csv"
pauseFlagPath := "C:\\Users\\baloghr\\Documents\\GitHub\\Weboldal\\runtime\\nettfront\\procurement\\a4830d3cdb26\\nettfront-helper.paused"
paused := false

SetPausedFlag(isPaused) {
    global pauseFlagPath
    try FileDelete pauseFlagPath
    if (isPaused)
        FileAppend "paused", pauseFlagPath, "UTF-8"
}

WaitWhilePaused() {
    global paused
    while paused
        Sleep 120
}

SetPausedFlag(false)

+Enter::
{
    global paused
    paused := !paused
    SetPausedFlag(paused)
    TrayTip "Divian-HUB import", paused ? "Szüneteltetve." : "Folytatva.", 1
}

+Space::
{
    global csvPath, sleeptime, doublesleeptime, paused
    if (paused) {
        TrayTip "Divian-HUB import", "A segéd jelenleg szünetel.", 1
        return
    }

    try content := FileRead(csvPath, "UTF-8")
    catch {
        MsgBox "Hiba: Nem sikerült beolvasni a fájlt: " csvPath
        return
    }

    lines := StrSplit(content, "`n", "`r")
    for _, line in lines
    {
        WaitWhilePaused()
        line := Trim(line)
        if (line = "")
            continue

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

        WaitWhilePaused()
        Send "{Tab 2}"
        Sleep sleeptime

        WaitWhilePaused()
        Send "^v"
        Sleep sleeptime

        WaitWhilePaused()
        Send "{Tab}"
        Sleep sleeptime

        WaitWhilePaused()
        A_Clipboard := mennyiseg
        Send "^v"
        Sleep sleeptime

        WaitWhilePaused()
        Send "{Tab}"
        Send "{Enter}"
        Sleep sleeptime
    }

    TrayTip "Divian-HUB import", "Az importálás befejeződött.", 2
}
