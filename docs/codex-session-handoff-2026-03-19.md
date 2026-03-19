# Codex Session Handoff - 2026-03-19

Ez a fájl a mai Codex munkamenet rövid átadása, hogy másik gépről is lásd, hol tart a projekt.

## Mai fontosabb javítások

### NettFront beszerzés
- Az előnézet már nem csak 12 sort mutat, hanem az összes beszerzési sort.
- A feltöltő oldalon már az első futásnál is lehet opcionális `alkatrészlista` fájlt feltölteni.
- A futó import-segédhez bekerült egy webes `Leállítás` gomb.
- Javítva lett a kódfeloldás logikája:
  - `Dfoz` / `Platt` csak a megfelelő speciális méretnél marad `NFAH`.
  - `NFAY <-> NFA` fallback két irányban működik.
  - színkód fallback is bekerült: `PRA <-> PRAS`, `KAF <-> KAFS`, `BGA <-> BGAS`, `GFA <-> GFAS`, `FEA <-> FEAS`.
  - megszűnt az a hiba, hogy a megtalált pontos kódot a fallback felülírta.

### Ellenőrzött konkrét esetek
- `718x197` kasmír már nem `NFAH`, hanem a megfelelő `NFA` kód.
- `824x590` és `720x355` most már feloldódik a feltöltött alkatrészlistából.
- A problémás teljes számlán a hiányzó kódok száma `28`-ról `0`-ra ment le tesztben.

## Fontos tudni a git verzióról
- A repo-ban a forráskód van.
- Nincs benne:
  - `runtime/`
  - `data/divian-ai/uploads/`
  - `__pycache__/`
- Emiatt a futási eredmények, lokális feltöltések és ideiglenes fájlok nem jönnek át automatikusan másik gépre.

## Ha másik gépen folytatod
1. `git pull origin main`
2. telepítsd a csomagokat:
   - `py -3 -m pip install -r requirements.txt`
3. indítsd a szervert:
   - `py -3 app.py`

## Megjegyzés
A tényleges Codex chat thread nem szinkronizálható gitből. Ez a fájl a beszélgetés gyakorlati átadása.
