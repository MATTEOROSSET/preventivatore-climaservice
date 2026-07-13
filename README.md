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

## Fonte dati impianto

Il flusso consigliato e' Odoo-first: il commerciale parte dal preventivo Odoo e apre il preventivatore dal pulsante/azione contestuale.

In questa modalita l'app legge direttamente dal preventivo Odoo:

- cliente e indirizzo
- prezzo totale
- righe prodotto
- tipo pannelli
- numero pannelli
- batteria

Il preventivatore usa questi dati come base e chiede solo di controllare i dati tecnici necessari ai calcoli, come potenza del singolo pannello e capacita' batteria.

## Catalogo locale di fallback

Le cartelle `listini/` e `schede_tecniche/` restano solo come supporto manuale se l'app viene aperta senza un preventivo Odoo collegato.

Nel flusso normale dei commerciali non sono la fonte principale: prezzi e prodotti devono essere governati da Odoo.

## Lettura bollette

Il caricatore accetta PDF, JPG e PNG.
I PDF testuali vengono letti direttamente; immagini e PDF scannerizzati richiedono OCR con Tesseract.
In cloud Tesseract viene installato tramite packages.txt.

## Integrazione Odoo CRM

Il preventivatore puo' essere aperto da un'opportunita Odoo aggiungendo al link:

```text
?opportunity_id=ID_OPPORTUNITA
```

Dal preventivo Odoo e' preferibile passare l'ID del preventivo:

```text
?order_id=ID_PREVENTIVO
```

Se i Secrets Odoo sono configurati su Streamlit Cloud, l'app legge cliente, indirizzo, totale del preventivo Odoo, tipo pannelli, numero pannelli e batteria dalle righe del preventivo e li usa come valori iniziali del calcolo. L'inverter non viene preso da Odoo perche' nel flusso Climaservice la distinzione commerciale principale e' pannelli + batterie.

I documenti generati e il riepilogo vengono salvati direttamente nel preventivo Odoo (`sale.order`). L'opportunita CRM non e' obbligatoria.

## Se non riparte

Fai doppio clic su:

CHIUDI_CLIMASERVICE.bat

poi riapri:

AVVIA_CLIMASERVICE.bat

Password: climaservice
