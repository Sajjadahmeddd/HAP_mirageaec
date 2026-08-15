# Packaging

Two outputs are supported. **The installer is what ships** (SharePoint
rollout); the single-file exe is kept for quick ad-hoc sharing.

## 1. Installer (recommended) — `dist\MAEC_HAPExt_Setup_v1.0.exe`

Requires Inno Setup 6 (installed at
`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`).

```powershell
# a) app bundle: folder build, starts in ~1.3 s (no self-extraction)
.\.venv\Scripts\pyinstaller --noconfirm --onedir --windowed `
    --name MAEC_HAPExt --icon "build\app.ico" `
    --add-data "config\mapping.json;." `
    --add-data "hap_converter\ui\assets;assets" `
    --distpath "build\app" run_app.py

# b) wrap it in the installer
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\installer.iss
```

Installer properties (see `build/installer.iss`): per-user install, **no
admin rights**, Start Menu + optional desktop shortcut, uninstall entry in
Settings → Apps, upgrades in place over an older version.

Measured startup: **1.3 s** (installed) vs **20–30 s** (one-file exe),
because the one-file build unpacks ~155 MB to temp on every launch.

## Code signing (once a certificate is available)

Signing removes the SmartScreen warning and satisfies Smart App Control,
which currently blocks the installer on machines that have it enabled.
Sign **both** the app exe and the finished installer.

```powershell
# 1. sign the app exe BEFORE compiling the installer
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
    /f company-cert.pfx /p <password> `
    "build\app\MAEC_HAPExt\MAEC_HAPExt.exe"

# 2. compile the installer (step 1b above), then sign it too
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
    /f company-cert.pfx /p <password> `
    "dist\MAEC_HAPExt_Setup_v1.0.exe"
```

`signtool.exe` ships with the Windows SDK. Always include the `/tr`
timestamp URL — without it the signature expires with the certificate.
Never commit the `.pfx` or its password to this repository.

Certificate options, cheapest first: a company-internal self-signed
certificate deployed to Trusted Publishers by Group Policy (free, works
only inside the company); Azure Trusted Signing (~$10/month); a
traditional OV/EV code-signing certificate (~$200-400/year, trusted
everywhere).

## 2. Single-file exe — `dist\MAEC_HAPExt.exe`

Portable, no installation at all, but slow to start. Build command
(produces ~72 MB, no Python required on the target machine):

```powershell
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\pyinstaller --noconfirm --onefile --windowed `
    --name MAEC_HAPExt --add-data "config\mapping.json;." `
    --add-data "hap_converter\ui\assets;assets" run_app.py
```

Notes:

- `run_app.py` is the top-level entry point (so the `hap_converter`
  package resolves inside the bundle).
- `mapping.json` is bundled INTO the exe, so the single file is fully
  self-contained. If a `mapping.json` is placed NEXT to the exe, it
  overrides the bundled one (user-editable config without rebuilding) —
  see `main.default_config_path`.
- First launch is slow (~10 s): the one-file exe unpacks itself to a temp
  folder. Subsequent launches are faster.
- To add an icon later: `--icon app.ico`.

## Sharing / clean-machine checklist

- Windows 10/11 with **no Python installed**; no admin rights needed.
- Copy just `MAEC_HAPExt.exe` anywhere and double-click.
- SmartScreen may warn on an unsigned exe — "More info → Run anyway"
  (code-signing removes this).
- Convert a real report; verify the CSV opens in Excel with `m²`/`°C`
  intact.
- Run twice into the same folder → second file must be `*_v1.csv`.
- Recent Projects history is stored per machine in
  `%APPDATA%\MAEC\recent_projects.json` — it does NOT travel with the exe.
