# Packaging (Step 10)

One-file windowed exe, mapping.json shipped alongside (stays user-editable):

```powershell
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\pyinstaller --onefile --windowed --name HAP_Converter `
    --icon app.ico hap_converter\main.py
Copy-Item config\mapping.json dist\
```

Ship `dist\HAP_Converter.exe` + `dist\mapping.json` together — the frozen app
loads `mapping.json` from the folder next to the exe
(see `main.default_config_path`).

## Clean-machine checklist

- Windows 10/11 with **no Python installed**.
- Copy the two files to any folder (no admin rights needed); double-click.
- Convert a real report; verify CSV opens in Excel with `m²`/`°C` intact.
- Delete `mapping.json` → app must show the configuration-error popup, not crash.
- Run twice into the same folder → second file must be `*_v1.csv`.
- SmartScreen may warn on an unsigned exe — "More info → Run anyway",
  or sign the binary.
