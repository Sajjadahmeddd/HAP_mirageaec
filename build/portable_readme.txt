MAEC — HAPExt   (portable version)
HAP "Zone Sizing Summary" PDF  ->  FCU schedule (Excel / CSV)
===============================================================

HOW TO RUN  (there is NO installation - you only extract once)
-------------------------------------------------------------
1. Right-click the downloaded .zip -> "Extract All..." and put the
   folder somewhere permanent, e.g. Documents.
   Do NOT run the app from inside the zip, and do not move
   MAEC_HAPExt.exe out of the folder - it needs the files beside it.
2. Open the extracted folder and double-click  MAEC_HAPExt.exe
3. Nothing to install. Python is NOT required.

Startup time: the FIRST launch can take 10-30 seconds while Windows
scans the new files. Every launch after that takes about 1 second.

TIP: right-click MAEC_HAPExt.exe -> "Pin to Start", or
     "Show more options > Send to > Desktop (create shortcut)".
     Then you can open the app from the Start menu / desktop
     without opening the folder each time.
     (If you later move the folder, recreate the shortcut.)

If Windows shows "Windows protected your PC":
   click "More info" -> "Run anyway".
   (The app is not code-signed yet, so Windows warns about it.
    It is safe: it runs fully offline and sends nothing anywhere.)

NEW PROJECT  -  PDF to schedule
-------------------------------
1. HAPExt card -> drag in (or Browse for) the HAP System Design PDF.
2. Click Upload, then Convert.
3. On the result screen click "Project Details" and fill in all
   9 fields, including your company logo image (PNG / JPG / JPEG).
4. Click Download and save as:
      Excel (.xlsx)  - full FCU schedule layout with your logo
      CSV (.csv)     - plain data only

CHANGE REQUEST  -  add a revised PDF to an existing schedule
------------------------------------------------------------
1. Select "Change Request" at the top of the upload screen.
2. Upload the previously generated .xlsx AND the revised PDF.
   (Use "Remove" on a card to swap in a different file.)
3. Click "Generate New Excel", then "Approve & Download".

No project details are asked for: the existing header block, revision
and company logo are carried over untouched. Existing rows are never
changed - only new line items are appended, and they are highlighted.

NOTES
-----
- Every value is copied exactly as printed in the PDF. No rounding.
- If any mandatory value is missing from the PDF, NOTHING is exported
  and the failure screen names the page and field. This is deliberate.
- Qty / ESP / FCU Types / Remarks are left blank for you to fill in.
- Works completely offline. No data leaves your computer.
- To remove the app: just delete this folder.
