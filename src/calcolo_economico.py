import pandas as pd


def calculate_cashflow(params):
    anni = int(params["anni_analisi"])
    rows = []

    investimento = params["costo_impianto"]
    contributo = 0
    if params["contributo_attivo"]:
        contributo = investimento * params["contributo_pct"] / 100
        if params["contributo_massimale"] > 0:
            contributo = min(contributo, params["contributo_massimale"])

    esborso = investimento - contributo

    detrazione_totale = 0
    detrazione_annua = 0
    if params["detrazione_attiva"]:
        detrazione_totale = investimento * params["detrazione_pct"] / 100
        detrazione_annua = detrazione_totale / max(1, params["anni_detrazione"])

    saldo = -esborso
    rows.append({
        "Anno": 0,
        "Produzione (kWh)": 0,
        "Costo energia (EUR)": 0,
        "Risparmio (EUR)": 0,
        "Ritiro dedicato (EUR)": 0,
        "Detrazione (EUR)": 0,
        "Manutenzione (EUR)": 0,
        "Flusso di cassa (EUR)": -esborso,
        "Saldo cumulativo (EUR)": saldo,
    })

    for anno in range(1, anni + 1):
        produzione = params["produzione_annua"] * ((1 - params["degrado_pct"] / 100) ** (anno - 1))
        costo_energia = params["costo_energia"] * ((1 + params["aumento_energia_pct"] / 100) ** (anno - 1))
        rid = params["rid"] * ((1 + params["aumento_energia_pct"] / 100) ** (anno - 1))
        autoconsumo = params["autoconsumo_pct"] / 100

        risparmio = produzione * autoconsumo * costo_energia
        ritiro = produzione * (1 - autoconsumo) * rid
        detrazione = detrazione_annua if anno <= params["anni_detrazione"] else 0
        manutenzione = params["manutenzione"] if anno % params["frequenza_manutenzione"] == 0 else 0

        flusso = risparmio + ritiro + detrazione - manutenzione
        saldo += flusso

        rows.append({
            "Anno": anno,
            "Produzione (kWh)": produzione,
            "Costo energia (EUR)": costo_energia,
            "Risparmio (EUR)": risparmio,
            "Ritiro dedicato (EUR)": ritiro,
            "Detrazione (EUR)": detrazione,
            "Manutenzione (EUR)": manutenzione,
            "Flusso di cassa (EUR)": flusso,
            "Saldo cumulativo (EUR)": saldo,
        })

    return pd.DataFrame(rows)


def break_even_year(df):
    pos = df[df["Saldo cumulativo (EUR)"] >= 0]
    if len(pos) == 0:
        return None
    return int(pos.iloc[0]["Anno"])
