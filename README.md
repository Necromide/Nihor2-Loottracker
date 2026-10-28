# Nihor2 - Loottracker

Ein lokales Tool für den Metin2-Server **Nihor2 – Chronicles of Jinteia**, das die Loot-Logs des Clients mitliest und auswertet: wie oft du welche Portale gelaufen bist, was dabei gedroppt ist, wie hoch die Drop-Raten sind – und wie oft dir ein **Super-Elite** begegnet ist.

*English version below.*

## Funktionen

- **Normaler Tracker** – wertet die komplette Historie aus (`info_chat_loot.log` + `loot_history_archive`) und importiert bei Bedarf weitere Logdateien.
- **Live-Tracker** – Start / Pause / Fortsetzen / Beenden. Es zählen nur Drops in der aktiven Live-Zeit; ein Run zählt, wenn sein Splinter in die Live-Zeit fällt. Sessions bleiben gespeichert und lassen sich vergleichen.
- **Portale** – Elite, Mystisch, Greater werden über ihren Splinter-Drop erkannt. Pro Item: Runs mit Drop, Rate mit 95-%-Bereich, Ø pro Run, Gesamt, Wert, Runs seit dem letzten Drop.
- **Super-Elite** – Erkennung über das eigene Drop-Paket (beide Skill Book Chests + Divine Blessing/Enchanting + Nataraja's Medallion, getrennt vom Splinter). Quote, Durststrecken, Liste aller Funde mit Sicherheit („Yang bestätigt“ / „Nur Signatur“ / „Keine Yang-Daten“).
- **Filter** – Zeitraum, Portale, Super-Elite, Sessions, Kategorie, Item-Suche, Wochentage, Uhrzeit, Mindest-Runs; Kisten-Inhalte und Drops außerhalb von Portalen jeweils ausblenden / einbeziehen / nur diese.
- **Besondere Drops** – *Begleiter Verhexen / Companion Bewitchment* (nur aus dem Elite-Endboss oder Super-Elite) und der Jackpot *Gürteltasche / Companion's Belt Satchel* (nur vom Super-Elite) mit eigener Quote. Gekaufte oder gehandelte Items zählen nicht.
- **Preise** (optional) pro Item → Wert pro Run und pro Stunde.
- **Aliase** – zwei Namen desselben Items zusammenführen (z. B. nach einem Wechsel der Client-Sprache).
- Deutsch / Englisch umschaltbar – und funktioniert mit **deutschem und englischem Client** (auch gemischt, wenn die Client-Sprache gewechselt wurde). Die deutschen Item-Namen werden automatisch den englischen zugeordnet.

Das Tool **liest den Client-Ordner nur** und greift nicht ins Spiel ein. Die Oberfläche läuft im Browser, ist aber nur auf deinem eigenen PC erreichbar (`127.0.0.1`).

## Installation

### Mit der .exe (empfohlen)

1. Unter **Releases** die Datei `Nihor2-Loottracker.exe` herunterladen und in einen eigenen Ordner legen (nicht in den Client-Ordner).
2. Starten. Windows zeigt beim ersten Mal evtl. „Der Computer wurde durch Windows geschützt“, weil die Datei nicht signiert ist → *Weitere Informationen* → *Trotzdem ausführen*.
3. Der Browser öffnet sich. Beim ersten Start den Client-Ordner auswählen (der Ordner mit `info_chat_loot.log`). Der erste Import dauert etwa eine Minute.

Das Konsolenfenster muss offen bleiben, solange du trackst. Die Daten liegen im Unterordner `data` neben der .exe.

### Aus dem Quellcode

Benötigt Python 3.10+ (keine weiteren Pakete).

```
python run.py            # oder start.bat
python run.py --help     # Optionen: --data, --client, --port, --no-browser
python -m unittest discover tests
```

### Eigene .exe bauen

```
pip install pyinstaller
pyinstaller loottracker.spec
```

Auf GitHub baut die Action `.github/workflows/build.yml` die .exe automatisch, sobald ein Release veröffentlicht oder ein Tag `v*` gepusht wird, und hängt sie an das Release.

## Wie die Erkennung funktioniert

| Was | Regel |
|---|---|
| Run | endet mit genau einem Splinter (Elite / Mystic / Greater). Start = erster Drop nach dem vorherigen Splinter, eine Pause > 5 min ohne Drops beginnt den Run später. |
| Normaler Boss | Drops in derselben Sekunde wie der Splinter |
| Super-Elite | beide Skill Book Chests + mind. 2 von Divine Blessing / Divine Enchanting / Nataraja's Medallion in derselben Sekunde, **nicht** zusammen mit dem Splinter; Zuordnung zum nächsten Elite-Splinter. Yang ≥ 1 Mio. bestätigt zusätzlich. |
| Kisten-Inhalte | Items aus der Liste „Kisten-Items“ (Standard: alle Skill Books / Lektüren) |
| Außerhalb Portale | Drops, die keinem Run zugeordnet sind – eine Schätzung |

Alle Regeln lassen sich unter *Einstellungen → Erkennungsregeln* anpassen, falls sich am Server etwas ändert.

---

## English

A local tool for the Metin2 server **Nihor2 – Chronicles of Jinteia**. It reads the client's loot logs and shows how often you ran which portal, what dropped, drop rates with confidence ranges and your **Super Elite** rate. Normal tracker for the full history, live tracker with sessions (start/pause/stop), filters, optional item prices, item aliases, German/English UI.

**Install:** download `Nihor2-Loottracker.exe` from *Releases*, put it in its own folder, run it, pick your client folder (the one containing `info_chat_loot.log`). Windows SmartScreen may warn because the exe is unsigned (*More info → Run anyway*). From source: `python run.py` (Python 3.10+, no dependencies).

The tool only reads the client folder and never touches the game. The web UI is only reachable from your own PC.

## Lizenz / License

MIT © 2026 Wilhelm Görlitz – siehe [LICENSE](LICENSE).
