# Készlet Intelligence – adatfeltöltési szerződés

## Cél

Az admin modul egységesen követi a készletszintet, készletértéket, készletforgást,
készletnapokat, fedezeti napokat, nem forgó készletet, hiánykockázatot és a
javasolt utánrendelési mennyiséget.

## Minden adatfrissítés tartalma

### 1. Termékek – kötelező

| Mező | Jelentés |
|---|---|
| Cikkszám | Tartós, egyedi cikkazonosító |
| Megnevezés | Ember által olvasható cikknév |
| Kategória | Vezetői és szűrési csoport |
| Mértékegység | db, m, m², kg stb. |
| Beszerzési egységár | Nettó, egységes pénznemben |
| Átfutási idő (nap) | Rendeléstől beérkezésig eltelt naptári nap |
| Biztonsági készlet | Az elvárt szolgáltatási szinthez fenntartott mennyiség |

A teljes aktív cikktörzset érdemes átadni. Ár, kategória, átfutási idő vagy
biztonsági készlet változásakor kötelező frissíteni.

### 2. Készlet – kötelező

| Mező | Jelentés |
|---|---|
| Dátum | A pillanatkép zárási napja |
| Raktár | A fizikai vagy logikai készlethely |
| Cikkszám | Kapcsolat a cikktörzzsel |
| Készlet | Könyv szerinti teljes mennyiség |
| Foglalt készlet | Már igényhez/rendeléshez rendelt mennyiség |

Minden aktív cikk–raktár kombináció szerepeljen, a nulla készletű is. Napi
pillanatkép a legjobb; heti pillanatkép a szakmai minimum.

### 3. Mozgások – kötelező

| Mező | Jelentés |
|---|---|
| Mozgás azonosító | Tartósan egyedi bizonylat- vagy mozgássor-azonosító |
| Dátum | Könyvelési dátum |
| Raktár | Érintett raktár |
| Cikkszám | Érintett cikk |
| Mozgástípus | Pl. bevételezés, eladás, anyagkiadás, selejt |
| Mennyiség | Mozgatott mennyiség; előjeles vagy pozitív is lehet |

Az első feltöltéshez legalább 90 nap, lehetőleg 12–24 hónap történet kell.
Ezután elegendők az új mozgások; az egyedi azonosító megakadályozza a
duplikált számítást.

### 4. Nyitott rendelések – ajánlott

| Mező | Jelentés |
|---|---|
| Rendeléssor azonosító | Tartósan egyedi beszerzési sorazonosító |
| Várható dátum | Aktuális visszaigazolt beérkezési dátum |
| Raktár | Célraktár |
| Cikkszám | Rendelt cikk |
| Nyitott mennyiség | Még be nem érkezett mennyiség |

Mindig a teljes aktuális nyitott állományt kell feltölteni. Ha a lap hiányzik,
a modul működik, de a hiánykockázat és a rendelési javaslat nem tud a várható
beérkezésekkel számolni.

## Alkalmazott számítások

- Elérhető készlet = teljes készlet − foglalt készlet.
- Készletérték = teljes készlet × aktuális beszerzési egységár.
- Készletforgás = időszaki kiadás értéke ÷ átlagos készletérték.
- Készletnap = vizsgált napok száma ÷ készletforgás.
- Fedezeti nap = elérhető készlet ÷ átlagos napi kiadás.
- Újrarendelési pont = átlagos napi kiadás × átfutási idő + biztonsági készlet.
- Javasolt rendelés = újrarendelési pont + 30 napi igény − elérhető − beérkező.
- ABC = időszaki kiadási érték szerinti kumulált fontosság.
- XYZ = heti felhasználás ingadozása szerinti kiszámíthatóság.

## Közösen véglegesítendő üzleti szabályok

1. Mely mozgástípusok számítanak valódi felhasználásnak vagy értékesítésnek?
2. Beszerzési ár, súlyozott átlagár vagy standard önköltség legyen az értékelési alap?
3. Naptári vagy munkanapos átfutási időt használjunk?
4. Mely raktárak eladhatóak, zároltak, minőségellenőrzés alatt állók vagy konszignációsak?
5. Mi legyen a cél-fedezet kategóriánként, és mely cikknél van minimum rendelési tétel/csomagolási egység?
6. A gyártási terv, vevői rendelés vagy előrejelzés is kerüljön-e a későbbi igénytervezésbe?
