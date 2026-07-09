# Deploy demo su Streamlit Cloud

## File da pubblicare

Caricare su GitHub solo questi elementi:

- app.py
- requirements.txt
- packages.txt
- README.md
- logo_climaservice.png
- src/
- templates/
- listini/
- schede_tecniche/
- .gitignore

Non caricare output, tmp_pdf, tmp_render, file di test o esempi generati.

## Impostazioni Streamlit Cloud

- Repository: quello creato su GitHub
- Branch: main
- Main file path: app.py

## Password

Password predefinita: climaservice

Per cambiarla da Streamlit Cloud, aprire Advanced settings / Secrets e inserire:

CLIMASERVICE_APP_PASSWORD = "nuova_password"

## Nota PDF commerciale

Il download Word e l'analisi economica PDF funzionano in cloud.
L'esportazione del preventivo commerciale Word in PDF richiede Microsoft Word installato sul server e quindi non e' garantita su Streamlit Cloud.

## OCR bollette

Il file packages.txt installa Tesseract e Poppler su Streamlit Cloud.
Servono per leggere bollette caricate come JPG/PNG o PDF scannerizzati.
