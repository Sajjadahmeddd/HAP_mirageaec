# Packaging

The working build command (produces `dist\MAEC_HAPExt.exe`, ~65 MB,
no Python required on the target machine):

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
