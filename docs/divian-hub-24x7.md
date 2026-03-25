# Divian-HUB 24/7 futtatás

Ha a fejlesztői gép ki van kapcsolva, a Divian-HUB nem tud futni. A valódi 0-24 megoldás az, hogy a projekt egy **mindig bekapcsolt irodai Windows gépen** fusson.

## Fontos

A gyártási modul jelenleg innen olvas:

- alapból: `V:\Output\Gyartasi_papirok`

24/7 futtatásnál ezt **nem érdemes** meghajtóbetűvel használni, mert a háttérfolyamatok és a startup taskok nem mindig látják a felcsatolt `V:` meghajtót.

Helyette a valódi hálózati elérési utat add meg, például:

- `\\szerver\Output\Gyartasi_papirok`

## Javasolt célgép

- irodai mini PC / mindig bekapcsolt Windows gép
- ugyanazon a hálózaton legyen, mint a `Gyartasi_papirok` megosztás
- az a Windows felhasználó, aki alatt a task fut, lássa az UNC megosztást

## Telepítés

1. Klónozd le a repót a célgépre.
2. Telepítsd a Python függőségeket.
3. Futáskor add meg az UNC gyökérutat.
4. Tedd fel a startup taskot.

### Függőségek

```powershell
py -3 -m pip install -r requirements.txt
```

### Egyszeri próbaindítás

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\divian_hub_runner.ps1 -ManufacturingRoot "\\szerver\Output\Gyartasi_papirok" -Port 5000
```

### 24/7 startup task telepítése

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_divian_hub_24x7_task.ps1 -UserName "CEG\\felhasznalo" -Password "jelszo" -ManufacturingRoot "\\szerver\Output\Gyartasi_papirok" -Port 5000
```

Ez a task:

- gépinduláskor elindítja a HUB-ot
- ha a folyamat leáll, újraindítja
- login nélkül is tud menni

## Hasznos fájlok

- indító runner: `tools/divian_hub_runner.ps1`
- user startup indító: `tools/start_divian_hub.ps1`
- leállítás: `tools/stop_divian_hub.ps1`
- 24/7 startup task telepítés: `tools/install_divian_hub_24x7_task.ps1`

## Megjegyzés

Ha a célgép fizikailag ki van kapcsolva, semmilyen script nem fogja futtatni az oldalt. A 0-24 futáshoz kell egy olyan gép, ami bekapcsolva marad.
