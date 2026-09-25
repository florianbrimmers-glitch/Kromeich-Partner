# Wireless Deploy aus Godot direkt aufs Handy

Ziel: keine APK mehr von GitHub Actions runterladen. Du druckst im Godot-
Editor einmal auf den Play-auf-Handy-Knopf und die aktuelle Version laeuft
in ~15 Sekunden auf deinem Phone.

Einmal-Setup, danach taeglich der Knopfdruck.

## Einmal-Setup (Schaetzung: 15 Minuten beim ersten Mal)

### 1. Android-SDK / Platform-Tools auf den PC

`adb` brauchst du auf dem PC, damit Godot mit dem Handy reden kann.

- **Mac**: `brew install --cask android-platform-tools`
- **Windows**: <https://developer.android.com/studio/releases/platform-tools>
  runterladen, ZIP entpacken, Ordner zum PATH hinzufuegen.
- **Linux**: `sudo apt install adb` (Debian/Ubuntu) oder via Distro-Paket.

Verifizieren: Terminal/Eingabeaufforderung -> `adb version` muss eine
Versionsnummer ausspucken.

### 2. Auf dem Handy: Entwickleroptionen + Wireless Debugging

1. *Einstellungen -> Telefoninfo -> Softwareinformationen*, dort 7 Mal auf
   *Build-Nummer* tippen, bis „Entwicklermodus aktiv" erscheint.
2. *Einstellungen -> Entwickleroptionen* oeffnen.
3. *Wireless Debugging* anschalten (auf Samsung-Geraeten: erst USB-Debugging
   einschalten, dann Wireless).

PC und Handy muessen im **gleichen WLAN** haengen.

### 3. Handy mit PC pairen (einmalig pro PC)

Auf dem Handy: *Wireless Debugging -> Mit Pairing-Code koppeln*. Da steht
dann:

```
IP-Adresse & Port: 192.168.X.Y:NNNNN
WLAN-Kopplungscode: 123456
```

Auf dem PC im Terminal:

```
adb pair 192.168.X.Y:NNNNN
```

Dann den 6-stelligen Code eingeben. Beim Erfolg: `Successfully paired ...`.

Dann verbinden (Achtung: das ist eine ANDERE Adresse/Port-Kombi, die auch
auf dem Handy direkt unter „Wireless Debugging" steht, NICHT die
Pairing-Adresse):

```
adb connect 192.168.X.Y:MMMMM
```

Check: `adb devices` muss dein Handy zeigen.

### 4. Godot-Editor: Android-Pfad konfigurieren

Im Editor: *Editor -> Editor Settings -> Export -> Android*.

- *Android SDK Path*: zeigt aufs Verzeichnis ueber `platform-tools`. Wenn du
  nur `adb` einzeln installiert hast, reicht der `platform-tools`-Ordner;
  Godot will eigentlich das ganze SDK, aber fuer reines Deploy/Run reicht
  oft schon ein Stub-Pfad - falls Godot meckert: das offizielle
  *Command-Line Tools only* von <https://developer.android.com/studio>
  installieren.
- *Debug Keystore*: Pfad zu `debug.keystore`. Wenn keiner existiert, einmal
  generieren:

  ```
  keytool -keyalg RSA -genkeypair -alias androiddebugkey \
          -keypass android -keystore debug.keystore -storepass android \
          -dname "CN=Android Debug,O=Android,C=US" -validity 9999
  ```

- *Debug Keystore User*: `androiddebugkey`
- *Debug Keystore Pass*: `android`

### 5. Export-Templates fuer Android installieren

*Editor -> Manage Export Templates -> Download and Install* (passt zur
Godot-Version, also 4.6 stable).

## Daily Driver

Nach dem Setup nur noch:

1. Im Editor unten rechts den Run-Target-Selektor auf das Handy stellen
   (Knopf neben dem Play-Symbol). Erscheint nach `adb connect`.
2. **F6** (oder „Play This Scene on remote") oder das Android-Icon oben
   rechts druecken.

Godot baut die APK lokal, pusht sie aufs Handy, startet sie. Beim ersten
Mal ~30 Sekunden, danach ~10-15 Sekunden Inkrement.

Wenn das Handy mal nicht erscheint: `adb connect 192.168.X.Y:MMMMM`
erneut ausfuehren (Wireless-Verbindung verliert sich nach Reboot/WLAN-Wechsel).

## Wann doch noch APK?

- Wenn du dem Bruder/der Freundin eine Version geben willst -> CI-APK.
- Wenn du eine Release-Build (signed, Play-Store-tauglich) brauchst.
- Sonst: der GitHub-Actions-Pfad ist nur noch fuer Sharing da, nicht fuer
  deinen eigenen Test-Loop.
