# Climaservice - Preventivatore Fotovoltaico

Web app Streamlit per generare preventivi fotovoltaici Climaservice partendo da bolletta, dati impianto, PVGIS e calcolo economico.

L'output finale e un documento Word basato sul modello ufficiale Climaservice. Le prime pagine del modello vengono mantenute, mentre il preventivatore aggiorna automaticamente:

- data del preventivo
- descrizione impianto
- pannelli, inverter, batteria e accumulo
- prezzo e incentivi
- grafici di produzione e ritorno economico
- prospetto sintetico del cashflow

## Avvio semplice

1. Apri la cartella dell'app.
3. Fai doppio clic su:

AVVIA_CLIMASERVICE.bat

4. Lascia aperta la finestra nera.
5. Usa il browser all'indirizzo:

http://localhost:8501

## Importante

La pagina localhost funziona solo mentre la finestra nera resta aperta.
Se chiudi la finestra nera, la web app si spegne.

Il modello Word usato per generare il preventivo si trova in:

templates/PR_fotovoltaico Trina SAJ.docx

## Listini e schede tecniche

I listini PDF vanno messi nella cartella:

listini/

Le schede tecniche PDF vanno messe nella cartella:

schede_tecniche/

Quando cambi o aggiungi un PDF in queste cartelle, il preventivatore rilegge i dati e aggiorna prezzi, configurazioni e descrizioni tecniche usate nella proposta Word.

Il flusso di scelta impianto parte dal pannello: scegli il tipo di pannello, imposti il numero di pannelli e il preventivatore calcola la potenza dell'impianto. Il listino viene usato per proporre il prezzo solo quando trova quella combinazione esatta di pannello e numero moduli.

Se una scheda tecnica non ha ancora una riga corrispondente nel listino, il prodotto compare comunque come voce "da scheda tecnica" nel menu. In quel caso il preventivatore compila marca, modello, potenza e descrizione tecnica, ma il prezzo resta da inserire/verificare manualmente.

## Lettura bollette

Il caricatore accetta PDF, JPG e PNG.
I PDF testuali vengono letti direttamente; immagini e PDF scannerizzati richiedono OCR con Tesseract.
In cloud Tesseract viene installato tramite packages.txt.

## Integrazione Odoo CRM

Il preventivatore puo' essere aperto da un'opportunita Odoo aggiungendo al link:

```text
?opportunity_id=ID_OPPORTUNITA
```

Se i Secrets Odoo sono configurati su Streamlit Cloud, l'app legge cliente e indirizzo dall'opportunita e permette di salvare in Odoo i documenti generati.

## Se non riparte

Fai doppio clic su:

CHIUDI_CLIMASERVICE.bat

poi riapri:

AVVIA_CLIMASERVICE.bat

Password: climaservice
