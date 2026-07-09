import os


APP_TITLE = "Climaservice - Dossier Fotovoltaico MVP V5"
PASSWORD = os.getenv("CLIMASERVICE_APP_PASSWORD", "climaservice")

BRAND_BLUE = "#071A3A"
BRAND_GOLD = "#C6A23A"
BRAND_DARK = "#1E2B28"
BRAND_GREY = "#F5F5F2"

DEFAULTS = {
    "aumento_energia_pct": 2.0,
    "rid": 0.12,
    "degrado_pct": 0.40,
    "manutenzione": 300.0,
    "frequenza_manutenzione": 2,
    "anni_analisi": 30,
    "costo_energia": 0.34,
    "autoconsumo_con_accumulo": 40.0,
    "autoconsumo_senza_accumulo": 25.0,
}

PRESET_INCENTIVI = {
    "Friuli - FVG + Detrazione 50%": {
        "contributo_attivo": True,
        "nome_contributo": "Contributo FVG",
        "contributo_pct": 40.0,
        "contributo_massimale": 0.0,
        "contributo_giorni": 60,
        "detrazione_attiva": True,
        "detrazione_pct": 50.0,
        "anni_detrazione": 10,
    },
    "Veneto - Solo detrazione 50%": {
        "contributo_attivo": False,
        "nome_contributo": "Nessun contributo",
        "contributo_pct": 0.0,
        "contributo_massimale": 0.0,
        "contributo_giorni": 0,
        "detrazione_attiva": True,
        "detrazione_pct": 50.0,
        "anni_detrazione": 10,
    },
    "Seconda casa - Detrazione 36%": {
        "contributo_attivo": False,
        "nome_contributo": "Nessun contributo",
        "contributo_pct": 0.0,
        "contributo_massimale": 0.0,
        "contributo_giorni": 0,
        "detrazione_attiva": True,
        "detrazione_pct": 36.0,
        "anni_detrazione": 10,
    },
    "Nessun incentivo": {
        "contributo_attivo": False,
        "nome_contributo": "Nessun contributo",
        "contributo_pct": 0.0,
        "contributo_massimale": 0.0,
        "contributo_giorni": 0,
        "detrazione_attiva": False,
        "detrazione_pct": 0.0,
        "anni_detrazione": 10,
    },
    "Personalizzato": {
        "contributo_attivo": True,
        "nome_contributo": "Contributo personalizzato",
        "contributo_pct": 0.0,
        "contributo_massimale": 0.0,
        "contributo_giorni": 60,
        "detrazione_attiva": True,
        "detrazione_pct": 50.0,
        "anni_detrazione": 10,
    },
}

COMPONENTI_SOLUZIONE = {
    "moduli": {
        "titolo": "Moduli fotovoltaici",
        "nome": "TRINA SOLAR 465 Wp",
        "dettagli": ["Garanzia prodotto 25 anni", "Garanzia produzione 30 anni"],
    },
    "inverter": {
        "titolo": "Inverter",
        "nome": "SAJ",
        "dettagli": ["Monitoraggio produzione", "Gestione impianto da app"],
    },
    "batteria": {
        "titolo": "Batteria",
        "nome": "SAJ 10 kWh",
        "dettagli": ["Accumulo energia serale", "Sistema modulare"],
    },
    "monitoraggio": {
        "titolo": "Monitoraggio",
        "nome": "App smartphone",
        "dettagli": ["Produzione e consumi sempre visibili"],
    },
    "installazione": {
        "titolo": "Installazione",
        "nome": "Chiavi in mano",
        "dettagli": ["Pratiche e collaudo inclusi"],
    },
}

VOCI_COMPRESE = [
    "Fornitura materiali",
    "Installazione",
    "Pratiche GSE",
    "Pratiche distributore",
    "Dichiarazione conformita",
    "Attivazione monitoraggio",
    "Assistenza post vendita",
]

PERCHE_CLIMASERVICE = [
    "Oltre 1.000 impianti realizzati",
    "Azienda presente sul territorio da oltre 13 anni",
    "Assistenza interna",
    "Nessun call center",
    "Manutentori dedicati",
    "363 recensioni Google",
]

GARANZIE = [
    ("Pannelli", "25 anni"),
    ("Produzione moduli", "30 anni"),
    ("Inverter", "Garanzia produttore"),
    ("Batteria", "Garanzia produttore"),
    ("Installazione Climaservice", "A norma di legge"),
]
