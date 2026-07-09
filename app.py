import os

import streamlit as st

from src.catalogo_prodotti import carica_catalogo, configurazione_da_pannello, prezzo_suggerito, prodotto_piu_vicino
from src.calcolo_economico import break_even_year, calculate_cashflow
from src.config import APP_TITLE, DEFAULTS, PASSWORD, PRESET_INCENTIVI
from src.estrazione_bolletta import extract_bill_data, extract_text_from_uploaded
from src.generatore_excel import genera_excel_ritorno
from src.generatore_analisi_pdf import genera_analisi_pdf
from src.generatore_word import (
    converti_word_in_pdf,
    default_template_path,
    genera_analisi_word,
    genera_preventivo_word,
)
from src.pvgis import call_pvgis, geocode_nominatim, pvgis_estimate_fallback, suggest_system
from src.utility_formattazione import euro, kwh


MONTH_LABELS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
MONTHLY_FALLBACK_DISTRIBUTION = [0.04, 0.055, 0.085, 0.105, 0.12, 0.13, 0.135, 0.12, 0.09, 0.065, 0.035, 0.02]
AUTOCONSUMO_CON_ACCUMULO_COEFF = 0.85
AUTOCONSUMO_SENZA_ACCUMULO_COEFF = 0.35


def produzione_mensile_stimata(produzione_annua, pvgis_values):
    if len(pvgis_values or []) == 12 and sum(float(value or 0) for value in pvgis_values) > 0:
        return [float(value or 0) for value in pvgis_values]

    distribution_total = sum(MONTHLY_FALLBACK_DISTRIBUTION)
    if distribution_total <= 0:
        return [float(produzione_annua or 0) / 12] * 12
    return [float(produzione_annua or 0) * share / distribution_total for share in MONTHLY_FALLBACK_DISTRIBUTION]


def consumi_mensili_da_annuo(consumi_annui):
    if float(consumi_annui or 0) <= 0:
        return []
    return [float(consumi_annui) / 12] * 12


def stima_autoconsumo_da_consumi(consumi_mensili, produzione_mensile, accumulo_kwh):
    produzione_totale = sum(float(value or 0) for value in produzione_mensile)
    if produzione_totale <= 0 or len(consumi_mensili or []) != 12 or len(produzione_mensile or []) != 12:
        return None

    energia_copribile = sum(
        min(float(consumo or 0), float(produzione or 0))
        for consumo, produzione in zip(consumi_mensili, produzione_mensile)
    )
    coefficiente = AUTOCONSUMO_CON_ACCUMULO_COEFF if float(accumulo_kwh or 0) > 0 else AUTOCONSUMO_SENZA_ACCUMULO_COEFF
    energia_autoconsumata = max(0.0, min(energia_copribile * coefficiente, produzione_totale))
    autoconsumo_pct = energia_autoconsumata / produzione_totale * 100
    return {
        "autoconsumo_pct": round(autoconsumo_pct, 1),
        "energia_autoconsumata": round(energia_autoconsumata),
        "energia_copribile": round(energia_copribile),
        "coefficiente": round(coefficiente * 100),
    }


@st.cache_data(show_spinner=False)
def carica_catalogo_cached(app_dir, signature):
    return carica_catalogo(app_dir)


def firma_catalogo(app_dir):
    app_dir = os.path.abspath(app_dir)
    project_dir = os.path.abspath(os.path.join(app_dir, os.pardir))
    folders = [
        project_dir,
        os.path.join(project_dir, "schede tecniche"),
        os.path.join(app_dir, "listini"),
        os.path.join(app_dir, "schede_tecniche"),
    ]
    items = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and name.lower().endswith(".pdf"):
                stat = os.stat(path)
                items.append((path, stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(items))


st.set_page_config(page_title=APP_TITLE, layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.6rem;
        padding-bottom: 2rem;
    }
    div.stButton > button, div.stDownloadButton > button {
        width: 100%;
        min-height: 2.7rem;
    }
    [data-testid="stMetric"] {
        background: #f6f8fb;
        border: 1px solid #e7ebf0;
        padding: 0.8rem 0.9rem;
        border-radius: 8px;
    }
    @media (max-width: 760px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        h1 {
            font-size: 1.55rem !important;
            line-height: 1.2 !important;
        }
        h2, h3 {
            font-size: 1.15rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "logged" not in st.session_state:
    st.session_state.logged = False

if not st.session_state.logged:
    st.title(APP_TITLE)
    pwd = st.text_input("Password", type="password")
    if st.button("Accedi"):
        if pwd == PASSWORD:
            st.session_state.logged = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()

logo_path = os.path.join(os.path.dirname(__file__), "logo_climaservice.png")
header_col_logo, header_col_title = st.columns([1, 5])
with header_col_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, width=170)
with header_col_title:
    st.title("Preventivatore Fotovoltaico Climaservice")
    st.caption("Calcolo rendimento, proposta economica e documenti commerciali")

if st.button("Nuovo preventivo / cancella dati caricati"):
    for key in list(st.session_state.keys()):
        if key != "logged":
            del st.session_state[key]
    st.rerun()

if st.button("Aggiorna listini e schede tecniche"):
    carica_catalogo_cached.clear()
    st.success("Listini e schede tecniche riletti.")
    st.rerun()

modalita_lavoro = st.radio(
    "Modalita lavoro",
    ["Preventivo rapido", "Preventivo dettagliato"],
    index=0,
    horizontal=True,
)
mostra_dettagli = modalita_lavoro == "Preventivo dettagliato"
st.caption(
    "Rapido: mostra solo i dati essenziali per arrivare al risultato. "
    "Dettagliato: apre anche verifiche, mensili, parametri tecnici e ipotesi economiche."
)

col1, col2 = st.columns([1, 1])
catalogo = carica_catalogo_cached(os.path.dirname(__file__), firma_catalogo(os.path.dirname(__file__)))

with col1:
    st.subheader("1. Bolletta")
    uploaded = st.file_uploader("Carica bolletta PDF o immagine", type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"], key="bolletta_pdf")
    extracted_text = extract_text_from_uploaded(uploaded, on_error=st.warning) if uploaded else ""
    bill = extract_bill_data(extracted_text) if extracted_text else {}

    if uploaded:
        anagrafica_ok = bool(bill.get("cliente") or bill.get("indirizzo") or bill.get("pod"))
        annuale_ok = bool(bill.get("consumi_annui_kwh"))
        mese_ok = bool(bill.get("consumo_mese_kwh"))
        costo_ok = bool(bill.get("costo_energia_stimato"))
        mensili = bill.get("consumi_mensili_kwh") or []
        mensili_ok = len(mensili) == 12

        status_rows = [
            {
                "Dato": "Dati anagrafici",
                "Esito": "OK" if anagrafica_ok else "Da compilare",
                "Valore": bill.get("cliente") or bill.get("pod") or "-",
            },
            {
                "Dato": "Consumo annuo",
                "Esito": "OK" if annuale_ok else "Stimato",
                "Valore": kwh(bill.get("consumi_annui_kwh")) if annuale_ok else "calcolato dal consumo periodo x 12",
            },
            {
                "Dato": "Consumo periodo bolletta",
                "Esito": "OK" if mese_ok else "Non letto",
                "Valore": kwh(bill.get("consumo_mese_kwh")) if mese_ok else "-",
            },
            {
                "Dato": "Consumi mese per mese",
                "Esito": "OK" if mensili_ok else "Non presenti / non letti",
                "Valore": "12 mesi letti" if mensili_ok else "il confronto usera' consumo annuo / 12",
            },
            {
                "Dato": "Costo energia",
                "Esito": "OK" if costo_ok else "Non letto",
                "Valore": f"{bill.get('costo_energia_stimato'):.3f} EUR/kWh" if costo_ok else "da inserire manualmente",
            },
        ]
        if anagrafica_ok or annuale_ok or mese_ok or costo_ok or mensili_ok:
            st.success("Bolletta caricata. Controlla e correggi sotto solo i dati mancanti.")
        else:
            st.warning("Bolletta caricata, ma i dati principali non sono stati letti. Compila manualmente i campi sotto.")

        with st.expander("Controllo lettura bolletta", expanded=mostra_dettagli):
            st.dataframe(status_rows, hide_index=True, use_container_width=True)
            if mensili_ok:
                st.caption("Consumi mensili letti dalla bolletta: " + " | ".join(kwh(value) for value in mensili))
            else:
                st.warning("Non ho trovato un dettaglio affidabile dei consumi mese per mese. Il grafico confrontera' la produzione mensile con una media mensile ottenuta dal consumo annuo.")

    cliente = st.text_input("Cliente", bill.get("cliente", ""))
    indirizzo = st.text_input("Indirizzo", bill.get("indirizzo", ""))
    localita = st.text_input("Localita", bill.get("localita", ""))
    pod = st.text_input("POD", bill.get("pod", ""))
    potenza_impegnata = st.number_input("Potenza impegnata (kW)", value=float(bill.get("potenza_impegnata") or 3.0), step=0.5)
    consumo_mese_default = float(bill.get("consumo_mese_kwh") or 0)
    consumi_annui_default = float(bill.get("consumi_annui_kwh") or (round(consumo_mese_default * 12) if consumo_mese_default else 0))
    costo_energia_default = float(bill.get("costo_energia_stimato") or 0)
    consumo_mese = st.number_input("Consumo mese bolletta (kWh)", value=consumo_mese_default, step=1.0)
    consumi_annui = st.number_input("Consumi annui stimati (kWh)", value=consumi_annui_default, step=100.0)
    costo_energia = st.number_input("Costo energia EUR/kWh", value=costo_energia_default, step=0.01, format="%.3f")

    with st.expander("Dettaglio fasce F1/F2/F3", expanded=mostra_dettagli):
        f1 = st.number_input("Consumo F1 periodo (kWh)", value=float(bill.get("f1") or 0), step=1.0)
        f2 = st.number_input("Consumo F2 periodo (kWh)", value=float(bill.get("f2") or 0), step=1.0)
        f3 = st.number_input("Consumo F3 periodo (kWh)", value=float(bill.get("f3") or 0), step=1.0)

    if bill.get("consumo_mese_kwh"):
        consumo_mese_fonte = bill.get("consumo_mese_fonte") or "Letto dalla bolletta"
    elif consumo_mese > 0:
        consumo_mese_fonte = "Inserito manualmente nel preventivatore"
    else:
        consumo_mese_fonte = "Non rilevato"

    if bill.get("consumi_annui_kwh"):
        consumi_annui_fonte = bill.get("consumi_annui_fonte") or "Letto dalla bolletta"
    elif consumo_mese_default and consumi_annui == round(consumo_mese_default * 12):
        consumi_annui_fonte = "Stimato dal consumo del periodo letto in bolletta moltiplicato per 12"
    elif consumi_annui > 0:
        consumi_annui_fonte = "Inserito manualmente nel preventivatore"
    else:
        consumi_annui_fonte = "Non rilevato"

    if bill.get("costo_energia_stimato"):
        costo_energia_fonte = bill.get("costo_energia_fonte") or "Letto/stimato dalla bolletta"
    elif costo_energia > 0:
        costo_energia_fonte = "Inserito manualmente nel preventivatore"
    else:
        costo_energia_fonte = "Non rilevato"

    with st.expander("Fonte dati usati nel calcolo"):
        st.dataframe(
            [
                {"Dato": "Consumo mese bolletta", "Valore": kwh(consumo_mese), "Fonte": consumo_mese_fonte},
                {"Dato": "Consumo annuo", "Valore": kwh(consumi_annui), "Fonte": consumi_annui_fonte},
                {"Dato": "Costo energia", "Valore": f"{costo_energia:.3f} EUR/kWh", "Fonte": costo_energia_fonte},
            ],
            hide_index=True,
            use_container_width=True,
        )

    bill_monthly_values = bill.get("consumi_mensili_kwh") or []
    default_monthly_values = bill_monthly_values if len(bill_monthly_values) == 12 else [0] * 12
    upload_signature = f"{uploaded.name}_{uploaded.size}" if uploaded else "manuale"
    consumi_mensili_input = []
    with st.expander("Consumi mese per mese", expanded=mostra_dettagli or len(bill_monthly_values) == 12):
        st.caption("Se la bolletta non li legge correttamente, inseriscili manualmente: saranno usati nel grafico di confronto con la produzione PVGIS.")
        monthly_cols = st.columns(4)
        for idx, label in enumerate(MONTH_LABELS):
            with monthly_cols[idx % 4]:
                value = st.number_input(
                    f"{label} kWh",
                    value=float(default_monthly_values[idx]),
                    step=1.0,
                    key=f"consumo_mensile_{upload_signature}_{idx}",
                )
                consumi_mensili_input.append(value)

    consumi_mensili_completi = all(value > 0 for value in consumi_mensili_input)
    mensili_letti_senza_modifiche = (
        len(bill_monthly_values) == 12
        and all(round(float(consumi_mensili_input[i]), 2) == round(float(bill_monthly_values[i]), 2) for i in range(12))
    )
    if consumi_mensili_completi and mensili_letti_senza_modifiche:
        consumi_mensili_fonte = bill.get("consumi_mensili_fonte") or "Dettaglio mensile letto dalla bolletta"
    elif consumi_mensili_completi:
        consumi_mensili_fonte = "Inseriti manualmente nel preventivatore"
    else:
        consumi_mensili_fonte = "Non rilevati"

    if consumi_annui <= 0 and consumi_mensili_completi:
        consumi_annui = sum(consumi_mensili_input)
        consumi_annui_fonte = f"Calcolato dalla somma dei 12 consumi mensili ({consumi_mensili_fonte})"
        st.info(f"Consumo annuo di calcolo ricavato dalla somma dei 12 mesi: {kwh(consumi_annui)}")

with col2:
    st.subheader("2. Consiglio impianto")
    obiettivo = st.selectbox(
        "Obiettivo cliente",
        ["Ridurre bolletta", "Massimizzare rendimento", "Massimizzare indipendenza energetica", "Auto elettrica futura", "Pompa di calore futura"],
    )
    suggested_kwp, suggested_batt = suggest_system(consumi_annui, obiettivo)
    st.info(f"Taglia consigliata: {suggested_kwp} kWp + batteria {suggested_batt} kWh")

    pannelli_catalogo = list(catalogo.get("pannelli", []))
    configurazioni_listino = list(catalogo["moduli"])
    batterie_listino = list(catalogo["batterie"]) + list(catalogo.get("batterie_da_schede", []))
    batteria_scelta = prodotto_piu_vicino(batterie_listino, suggested_batt, "capacita_kwh")

    if pannelli_catalogo:
        labels_pannelli = [
            f"{item['tipo_pannelli']} - {item['potenza_pannello_wp']:.0f} Wp"
            f"{' - da scheda tecnica' if item.get('solo_scheda') else ''}"
            for item in pannelli_catalogo
        ]
        pannello_default = pannelli_catalogo[0]
        selected_panel_idx = st.selectbox(
            "Tipo pannello",
            range(len(pannelli_catalogo)),
            index=0,
            format_func=lambda idx: labels_pannelli[idx],
        )
        pannello_scelto = pannelli_catalogo[selected_panel_idx]
    else:
        st.warning("Nessun pannello trovato da listini o schede tecniche. Inserisci i dati impianto manualmente.")
        pannello_scelto = {}

    if batterie_listino:
        labels_batterie = ["Nessuna batteria"] + [
            (
                f"{item['marca_modello']} - {item['capacita_kwh']:.1f} kWh - "
                f"{'prezzo manuale' if item.get('solo_scheda') else euro(item['prezzo_nuovo'])}"
            )
            for item in batterie_listino
        ]
        default_batt_idx = batterie_listino.index(batteria_scelta) + 1 if batteria_scelta in batterie_listino else 0
        selected_batt_idx = st.selectbox(
            "Batteria",
            range(len(labels_batterie)),
            index=default_batt_idx,
            format_func=lambda idx: labels_batterie[idx],
        )
        batteria_scelta = batterie_listino[selected_batt_idx - 1] if selected_batt_idx > 0 else None
    else:
        batteria_scelta = None

    with st.expander("Dettagli tecnici pannello e inverter", expanded=mostra_dettagli):
        tipo_pannelli = st.text_input("Tipo pannelli", pannello_scelto.get("tipo_pannelli", "TRINA SOLAR"))
        modello_pannelli = st.text_input("Modello pannelli", pannello_scelto.get("modello_pannelli", "TSM-NEG9R.28"))
        potenza_pannello_wp = st.number_input("Potenza singolo pannello (Wp)", value=float(pannello_scelto.get("potenza_pannello_wp") or 465.0), step=5.0)
    numero_pannelli_default = max(1, int(round(suggested_kwp * 1000 / max(potenza_pannello_wp, 1))))
    numero_pannelli = st.number_input("Numero pannelli", value=numero_pannelli_default, step=1)
    potenza_kwp_calcolata = round(float(numero_pannelli) * float(potenza_pannello_wp) / 1000, 2)
    st.metric("Potenza impianto", f"{potenza_kwp_calcolata:.2f} kWp")
    potenza_kwp = potenza_kwp_calcolata
    configurazione_scelta = configurazione_da_pannello(configurazioni_listino, pannello_scelto, numero_pannelli)
    if not configurazione_scelta:
        configurazione_scelta = {**pannello_scelto, "numero_pannelli": int(numero_pannelli), "potenza_kwp": potenza_kwp, "prezzo_iva": 0}
    moduli = f"{numero_pannelli} x {potenza_pannello_wp:.0f} W"
    with st.expander("Modifica potenza o inverter", expanded=mostra_dettagli):
        potenza_kwp = st.number_input("Potenza impianto proposta (kWp)", value=float(potenza_kwp_calcolata), step=0.01)
        inverter = st.text_input("Inverter", configurazione_scelta.get("inverter") or pannello_scelto.get("inverter", "SAJ"))
    batteria_default = batteria_scelta.get("marca_modello") if batteria_scelta else "Nessuna batteria"
    batteria = st.text_input("Batteria", batteria_default)
    accumulo_kwh = st.number_input("Accumulo (kWh)", value=float((batteria_scelta or {}).get("capacita_kwh") or 0), step=1.0)
    prezzo_listino = prezzo_suggerito(configurazione_scelta, batteria_scelta)
    prezzo_help = "Prezzo suggerito da listino in base a tipo pannello, numero pannelli e accumulo" if prezzo_listino else "Prezzo da inserire manualmente: combinazione non trovata nel listino"
    costo_impianto = st.number_input("Costo impianto IVA compresa (EUR)", value=float(prezzo_listino or 13900.0), step=100.0, help=prezzo_help)
    with st.expander("Dettaglio prezzo e schede tecniche"):
        st.write(f"Prezzo moduli/inverter da listino: {euro(configurazione_scelta.get('prezzo_iva') or 0)}")
        st.write(f"Prezzo accumulo da listino: {euro((batteria_scelta or {}).get('prezzo_nuovo') or 0)}")
        if configurazione_scelta.get("solo_scheda") or (batteria_scelta or {}).get("solo_scheda") or not configurazione_scelta.get("prezzo_iva"):
            st.warning("Uno o piu' prodotti arrivano solo da scheda tecnica o non hanno una riga prezzo esatta: il prezzo va inserito o verificato manualmente.")
        st.write(f"Fonte listino: {configurazione_scelta.get('fonte_listino') or 'Non rilevata'}")
        if configurazione_scelta.get("scheda_tecnica"):
            st.write(f"Scheda pannelli: {configurazione_scelta['scheda_tecnica']}")
        if (batteria_scelta or {}).get("scheda_tecnica"):
            st.write(f"Scheda batteria: {batteria_scelta['scheda_tecnica']}")

st.subheader("3. Localizzazione e PVGIS reale")
indirizzo_pvgis = st.text_input("Indirizzo impianto", f"{indirizzo}, {localita}, Italia")
with st.expander("Dati tecnici PVGIS", expanded=mostra_dettagli):
    gc1, gc2, gc3 = st.columns(3)
    with gc1:
        orientamento = st.number_input("Orientamento PVGIS", value=0.0, step=1.0, help="0=sud, +/-90 est/ovest, 180 nord")
    with gc2:
        inclinazione = st.number_input("Inclinazione", value=25.0, step=1.0)
    with gc3:
        perdite = st.number_input("Perdite sistema %", value=14.0, step=1.0)

if "lat" not in st.session_state:
    st.session_state.lat = 46.138
    st.session_state.lon = 12.890
if "pvgis_annual" not in st.session_state:
    st.session_state.pvgis_annual = None
    st.session_state.pvgis_values = []

def aggiorna_pvgis(lat_value, lon_value):
    annual, months, values, err = call_pvgis(lat_value, lon_value, potenza_kwp, inclinazione, orientamento, perdite)
    if err:
        st.warning(f"PVGIS non disponibile, uso stima provvisoria. Errore: {err}")
        annual = pvgis_estimate_fallback(potenza_kwp, orientamento, inclinazione)
        values = []
    st.session_state.pvgis_annual = annual
    st.session_state.pvgis_values = values
    st.success(f"PVGIS calcolato: {annual:.0f} kWh/anno")


if st.button("Calcola produzione da indirizzo"):
    lat_found, lon_found = geocode_nominatim(indirizzo_pvgis, on_error=st.warning)
    if lat_found is None:
        st.warning("Coordinate non trovate. Inserisci latitudine e longitudine manualmente e usa il calcolo da coordinate.")
    else:
        st.session_state.lat, st.session_state.lon = lat_found, lon_found
        aggiorna_pvgis(lat_found, lon_found)

with st.expander("Coordinate manuali", expanded=mostra_dettagli):
    lat_col, lon_col = st.columns(2)
    lat = lat_col.number_input("Latitudine", value=float(st.session_state.lat), format="%.6f")
    lon = lon_col.number_input("Longitudine", value=float(st.session_state.lon), format="%.6f")
    st.session_state.lat, st.session_state.lon = lat, lon
    if st.button("Calcola PVGIS con coordinate manuali"):
        aggiorna_pvgis(lat, lon)

produzione_default = st.session_state.pvgis_annual or pvgis_estimate_fallback(potenza_kwp, orientamento, inclinazione)
produzione_annua = st.number_input("Produzione annua usata nel calcolo (kWh)", value=float(round(produzione_default)), step=10.0)

st.subheader("4. Incentivi e agevolazioni")
preset = st.selectbox("Preset incentivi", list(PRESET_INCENTIVI.keys()))
p = PRESET_INCENTIVI[preset]

with st.expander("Dettaglio incentivi", expanded=mostra_dettagli or preset == "Personalizzato"):
    ic1, ic2, ic3, ic4 = st.columns(4)
    contributo_attivo = ic1.checkbox("Contributo attivo", value=p["contributo_attivo"])
    nome_contributo = ic2.text_input("Nome contributo", value=p["nome_contributo"])
    contributo_pct = ic3.number_input("Contributo %", value=float(p["contributo_pct"]), step=1.0)
    contributo_giorni = ic4.number_input("Incasso contributo (giorni)", value=int(p["contributo_giorni"]), step=10)
    contributo_massimale = st.number_input("Massimale contributo (EUR) - 0 se assente", value=float(p["contributo_massimale"]), step=100.0)

    dc1, dc2, dc3 = st.columns(3)
    detrazione_attiva = dc1.checkbox("Detrazione attiva", value=p["detrazione_attiva"])
    detrazione_pct = dc2.number_input("Detrazione %", value=float(p["detrazione_pct"]), step=1.0)
    anni_detrazione = dc3.number_input("Numero rate/anni", value=int(p["anni_detrazione"]), step=1)

st.subheader("5. Parametri economici")
ec1, ec2, ec3, ec4 = st.columns(4)
produzione_mensile_calcolo = produzione_mensile_stimata(produzione_annua, st.session_state.pvgis_values)
consumi_mensili_calcolo = consumi_mensili_input if consumi_mensili_completi else consumi_mensili_da_annuo(consumi_annui)
autoconsumo_stima = stima_autoconsumo_da_consumi(
    consumi_mensili_calcolo,
    produzione_mensile_calcolo,
    accumulo_kwh,
)
if autoconsumo_stima is not None:
    autoconsumo_pct = autoconsumo_stima["autoconsumo_pct"]
    autoconsumo_kwh = autoconsumo_stima["energia_autoconsumata"]
    autoconsumo_coefficiente = autoconsumo_stima["coefficiente"]
    if consumi_mensili_completi:
        autoconsumo_fonte = (
            f"Calcolato mese per mese da consumi bolletta e produzione stimata, con coefficiente {autoconsumo_coefficiente}%"
        )
    else:
        autoconsumo_fonte = (
            f"Stimato da consumo annuo ripartito su 12 mesi e produzione stimata, con coefficiente {autoconsumo_coefficiente}%"
        )
    ec1.metric("Autoconsumo stimato", f"{autoconsumo_pct:.1f}%")
    ec1.caption(f"{kwh(autoconsumo_kwh)} autoconsumati")
    st.caption(
        "Autoconsumo calcolato automaticamente: prima confronto mese per mese tra consumi e produzione, "
        f"poi applico il coefficiente prudenziale del {autoconsumo_coefficiente}% perche' non si autoconsuma mai il 100%."
    )
else:
    autoconsumo_default = DEFAULTS["autoconsumo_con_accumulo"] if accumulo_kwh > 0 else DEFAULTS["autoconsumo_senza_accumulo"]
    autoconsumo_pct = ec1.number_input("Autoconsumo ipotizzato %", value=autoconsumo_default, step=1.0)
    autoconsumo_kwh = round(float(produzione_annua or 0) * float(autoconsumo_pct or 0) / 100)
    autoconsumo_fonte = "Ipotizzato manualmente per assenza di consumi utilizzabili"
    st.warning(
        "Autoconsumo da ipotizzare: non ci sono consumi annui o mensili utilizzabili. "
        "Inserisci il consumo annuo o i consumi mese per mese nella sezione bolletta per farlo calcolare automaticamente."
    )
with st.expander("Ipotesi economiche avanzate", expanded=mostra_dettagli):
    ac1, ac2, ac3 = st.columns(3)
    rid = ac1.number_input("Ritiro dedicato EUR/kWh", value=DEFAULTS["rid"], step=0.01, format="%.3f")
    aumento_energia_pct = ac2.number_input("Aumento energia annuo %", value=DEFAULTS["aumento_energia_pct"], step=0.5)
    degrado_pct = ac3.number_input("Degrado pannelli annuo %", value=DEFAULTS["degrado_pct"], step=0.05)
    mc1, mc2 = st.columns(2)
    manutenzione = mc1.number_input("Costo manutenzione (EUR)", value=DEFAULTS["manutenzione"], step=50.0)
    frequenza_manutenzione = mc2.number_input("Frequenza manutenzione (anni)", value=DEFAULTS["frequenza_manutenzione"], step=1)

params = {
    "costo_impianto": costo_impianto,
    "contributo_attivo": contributo_attivo,
    "nome_contributo": nome_contributo,
    "contributo_pct": contributo_pct,
    "contributo_massimale": contributo_massimale,
    "detrazione_attiva": detrazione_attiva,
    "detrazione_pct": detrazione_pct,
    "anni_detrazione": int(anni_detrazione),
    "autoconsumo_pct": autoconsumo_pct,
    "costo_energia": costo_energia,
    "aumento_energia_pct": aumento_energia_pct,
    "rid": rid,
    "degrado_pct": degrado_pct,
    "manutenzione": manutenzione,
    "frequenza_manutenzione": int(frequenza_manutenzione),
    "anni_analisi": DEFAULTS["anni_analisi"],
    "produzione_annua": produzione_annua,
}

df = calculate_cashflow(params)
be = break_even_year(df)
anno1 = df[df["Anno"] == 1].iloc[0]
beneficio_annuo = anno1["Risparmio (EUR)"] + anno1["Ritiro dedicato (EUR)"]
beneficio_30 = df[df["Anno"] == 30]["Saldo cumulativo (EUR)"].iloc[0]
contributo = costo_impianto * contributo_pct / 100 if contributo_attivo else 0
if contributo_massimale > 0:
    contributo = min(contributo, contributo_massimale)
detrazione_totale = costo_impianto * detrazione_pct / 100 if detrazione_attiva else 0
esborso_netto = costo_impianto - contributo
spesa_annua_stimata = consumi_annui * costo_energia

st.subheader("6. Riepilogo proposta")
r1, r2, r3, r4 = st.columns(4)
r1.metric("Impianto", f"{potenza_kwp:.2f} kWp", f"{int(numero_pannelli)} pannelli")
r2.metric("Accumulo", f"{accumulo_kwh:.0f} kWh" if accumulo_kwh else "No")
r3.metric("Prezzo IVA compresa", euro(costo_impianto))
r4.metric("Produzione stimata", kwh(produzione_annua))

rr1, rr2, rr3, rr4 = st.columns(4)
rr1.metric("Autoconsumo", f"{autoconsumo_pct:.1f}%", kwh(autoconsumo_kwh))
rr2.metric("Beneficio anno 1", euro(beneficio_annuo))
rr3.metric("Pareggio", f"Anno {be}" if be else "Oltre analisi")
rr4.metric("Beneficio 30 anni", euro(beneficio_30))

st.subheader("7. Anteprima economica")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Beneficio anno 1", euro(beneficio_annuo))
m2.metric("Pareggio", f"Anno {be}")
m3.metric("Beneficio 30 anni", euro(beneficio_30))
m4.metric("PVGIS", kwh(produzione_annua))
m5.metric("Esborso dopo contributo", euro(esborso_netto))
st.line_chart(df.set_index("Anno")["Saldo cumulativo (EUR)"])

with st.expander("Tabella ritorno economico"):
    st.dataframe(df, use_container_width=True)
    excel_ritorno = genera_excel_ritorno(df)
    st.download_button(
        "Scarica tabella ritorno economico Excel",
        data=excel_ritorno,
        file_name="Tabella_Ritorno_Economico.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.subheader("8. Genera documenti")
st.info("Vengono generati due documenti: offerta commerciale discorsiva e allegato tecnico con analisi rendimento/ritorno economico.")

data = {
    "cliente": cliente,
    "indirizzo": indirizzo,
    "localita": localita,
    "pod": pod,
    "consumi_annui": consumi_annui,
    "consumi_annui_fonte": consumi_annui_fonte,
    "consumo_mese": consumo_mese,
    "consumo_mese_fonte": consumo_mese_fonte,
    "consumi_mensili": consumi_mensili_input if consumi_mensili_completi else [],
    "consumi_mensili_fonte": consumi_mensili_fonte,
    "spesa_annua_stimata": spesa_annua_stimata,
    "potenza_kwp": potenza_kwp,
    "moduli": moduli,
    "accumulo_kwh": accumulo_kwh,
    "produzione_annua": produzione_annua,
    "costo_impianto": costo_impianto,
    "nome_contributo": nome_contributo,
    "contributo_pct": contributo_pct,
    "contributo": contributo,
    "detrazione_pct": detrazione_pct,
    "anni_detrazione": int(anni_detrazione),
    "detrazione_totale": detrazione_totale,
    "esborso_netto": esborso_netto,
    "beneficio_annuo": beneficio_annuo,
    "beneficio_30": beneficio_30,
    "break_even": be,
    "risparmio_anno1": anno1["Risparmio (EUR)"],
    "ritiro_anno1": anno1["Ritiro dedicato (EUR)"],
    "autoconsumo_pct": autoconsumo_pct,
    "autoconsumo_kwh": autoconsumo_kwh,
    "autoconsumo_fonte": autoconsumo_fonte,
    "costo_energia": costo_energia,
    "costo_energia_fonte": costo_energia_fonte,
    "aumento_energia_pct": aumento_energia_pct,
    "rid": rid,
}

impianto = {
    "numero_pannelli": int(numero_pannelli),
    "tipo_pannelli": tipo_pannelli,
    "modello_pannelli": modello_pannelli,
    "potenza_pannello_wp": potenza_pannello_wp,
    "potenza_kwp": potenza_kwp,
    "inverter": inverter,
    "batteria": batteria,
    "accumulo_kwh": accumulo_kwh,
    "descrizione_moduli": configurazione_scelta.get("descrizione_tecnica", ""),
    "descrizione_batteria": (batteria_scelta or {}).get("descrizione_tecnica", ""),
    "fonte_listino": configurazione_scelta.get("fonte_listino", ""),
    "scheda_moduli": configurazione_scelta.get("scheda_tecnica", ""),
    "scheda_batteria": (batteria_scelta or {}).get("scheda_tecnica", ""),
}

template_path = default_template_path(os.path.dirname(__file__))
if not template_path.exists():
    st.error(f"Template Word non trovato: {template_path}")
    st.stop()

docx = genera_preventivo_word(template_path, data, df, impianto, st.session_state.pvgis_values)
analisi_docx = genera_analisi_word(data, df, impianto, st.session_state.pvgis_values)
analisi_pdf = genera_analisi_pdf(data, df, impianto, st.session_state.pvgis_values)
base_filename = cliente.replace(" ", "_")

dl1, dl2, dl3, dl4 = st.columns(4)
with dl1:
    st.download_button(
        "Scarica offerta commerciale Word",
        data=docx,
        file_name=f"Offerta_Commerciale_Fotovoltaico_{base_filename}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
with dl2:
    st.download_button(
        "Scarica analisi economica PDF",
        data=analisi_pdf,
        file_name=f"Analisi_Rendimento_Fotovoltaico_{base_filename}.pdf",
        mime="application/pdf",
    )
with dl3:
    st.download_button(
        "Scarica analisi economica Word",
        data=analisi_docx,
        file_name=f"Analisi_Rendimento_Fotovoltaico_{base_filename}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
with dl4:
    pdf_offerta_key = f"{base_filename}_{costo_impianto}_{potenza_kwp}_{numero_pannelli}"
    if st.button("Prepara offerta commerciale PDF"):
        try:
            with st.spinner("Esporto il Word commerciale in PDF..."):
                st.session_state.pdf_offerta = converti_word_in_pdf(docx.getvalue(), work_dir=os.path.dirname(__file__))
                st.session_state.pdf_offerta_key = pdf_offerta_key
        except Exception as exc:
            st.session_state.pdf_offerta = None
            st.session_state.pdf_offerta_key = None
            st.error(f"PDF offerta non generato: {exc}")
    if st.session_state.get("pdf_offerta") and st.session_state.get("pdf_offerta_key") == pdf_offerta_key:
        st.download_button(
            "Scarica offerta commerciale PDF",
            data=st.session_state.pdf_offerta,
            file_name=f"Offerta_Commerciale_Fotovoltaico_{base_filename}.pdf",
            mime="application/pdf",
        )
    else:
        st.caption("Il PDF viene esportato dal file Word commerciale, mantenendo lo stesso layout.")
