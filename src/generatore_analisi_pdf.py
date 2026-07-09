from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


BLUE = "#17365D"
GOLD = "#C6A23A"
GREY = "#F4F4F1"
DARK = "#202A25"


def eur(value, decimals=0):
    try:
        if decimals:
            return f"EUR {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"EUR {value:,.0f}".replace(",", ".")
    except Exception:
        return "EUR 0"


def kwh(value):
    try:
        return f"{value:,.0f} kWh".replace(",", ".")
    except Exception:
        return "0 kWh"


def genera_analisi_pdf(data, df, impianto, monthly_values=None):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    logo_path = Path(__file__).resolve().parent.parent / "logo_climaservice.png"

    def header(title, page_no):
        c.setFillColor(colors.HexColor(BLUE))
        c.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)
        if logo_path.exists():
            c.drawImage(
                ImageReader(str(logo_path)),
                10 * mm,
                h - 14.3 * mm,
                width=43 * mm,
                height=9 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(58 * mm, h - 11 * mm, title)
        c.drawRightString(w - 14 * mm, h - 11 * mm, f"Pagina {page_no}")

    def section(code, title, subtitle=None):
        c.setFillColor(colors.HexColor(DARK))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(18 * mm, h - 38 * mm, code)
        c.setFont("Helvetica-Bold", 22)
        y = h - 54 * mm
        for line in title:
            c.drawString(18 * mm, y, line)
            y -= 9 * mm
        if subtitle:
            c.setFont("Helvetica", 10)
            draw_wrapped(subtitle, 18 * mm, y - 2 * mm, 172 * mm, 5 * mm)

    def draw_wrapped(text, x, y, max_width, leading=5 * mm, font="Helvetica", size=10):
        c.setFont(font, size)
        words = str(text).split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if c.stringWidth(candidate, font, size) <= max_width:
                line = candidate
            else:
                c.drawString(x, y, line)
                y -= leading
                line = word
        if line:
            c.drawString(x, y, line)
            y -= leading
        return y

    def metric_box(x, y, label, value, note="", width=52 * mm):
        c.setStrokeColor(colors.HexColor("#D9D9D9"))
        c.setFillColor(colors.white)
        c.roundRect(x, y - 28 * mm, width, 28 * mm, 3 * mm, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#777777"))
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 5 * mm, y - 7 * mm, label)
        c.setFillColor(colors.HexColor(BLUE))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x + 5 * mm, y - 17 * mm, str(value))
        c.setFillColor(colors.HexColor("#666666"))
        c.setFont("Helvetica", 7)
        c.drawString(x + 5 * mm, y - 24 * mm, str(note)[:42])

    def simple_table(x, y, rows, col_widths, row_h=8 * mm, header_fill=BLUE):
        for ri, row in enumerate(rows):
            xx = x
            for ci, value in enumerate(row):
                fill = header_fill if ri == 0 else ("#F7F7F7" if ri % 2 == 0 else "#FFFFFF")
                c.setFillColor(colors.HexColor(fill))
                c.setStrokeColor(colors.HexColor("#DDDDDD"))
                c.rect(xx, y - row_h, col_widths[ci], row_h, fill=1, stroke=1)
                c.setFillColor(colors.white if ri == 0 else colors.HexColor(DARK))
                c.setFont("Helvetica-Bold" if ri == 0 else "Helvetica", 8)
                c.drawString(xx + 2 * mm, y - 5.2 * mm, str(value)[:42])
                xx += col_widths[ci]
            y -= row_h
        return y

    def source_note(value, fallback="Inserito manualmente"):
        return str(value or fallback)[:42]

    monthly_values = _monthly_values(monthly_values, data["produzione_annua"])
    be = data.get("break_even")
    consumi_annui = float(data.get("consumi_annui") or 0)
    if consumi_annui <= 0:
        consumi_annui = max(float(data.get("spesa_annua_stimata") or 0) / max(float(data.get("costo_energia") or 0.34), 0.01), 1)
    autoconsumo_pct = float(data.get("autoconsumo_pct") or 0) / 100
    copertura = min(data["produzione_annua"] / consumi_annui * 100, 100)
    autonomia = min(data["produzione_annua"] * autoconsumo_pct / consumi_annui * 100, 100)
    anno1 = df[df["Anno"] == 1].iloc[0]
    risparmio_autoconsumo = float(anno1["Risparmio (EUR)"])
    ricavo_energia = float(anno1["Ritiro dedicato (EUR)"])
    bolletta_residua = max(
        float(data["spesa_annua_stimata"]) - risparmio_autoconsumo,
        float(data["spesa_annua_stimata"]) * 0.15,
        120,
    )
    risparmio_10 = float(df[df["Anno"] == 10]["Saldo cumulativo (EUR)"].iloc[0])
    co2_kg = float(data["produzione_annua"]) * 0.33
    alberi = co2_kg / 22
    km_auto = co2_kg / 0.12
    consumi_annui_fonte = data.get("consumi_annui_fonte") or "Inserito manualmente nel preventivatore"
    consumo_mese_fonte = data.get("consumo_mese_fonte") or "Inserito manualmente nel preventivatore"
    costo_energia_fonte = data.get("costo_energia_fonte") or "Inserito manualmente nel preventivatore"
    autoconsumo_fonte = data.get("autoconsumo_fonte") or "Inserito manualmente nel preventivatore"
    autoconsumo_kwh = float(data.get("autoconsumo_kwh") or data["produzione_annua"] * autoconsumo_pct)

    # Page 1 - summary
    c.setFillColor(colors.HexColor(GREY))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    header("Preventivo fotovoltaico personalizzato", 1)
    section(
        "PROPOSTA SU MISURA",
        ["La tua simulazione", "energetica personalizzata"],
        "La proposta economica e' costruita su consumi reali, produzione stimata e parametri economici modificabili.",
    )
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica", 11)
    draw_wrapped(
        f"Abbiamo progettato questa soluzione per {data.get('cliente', 'il cliente')} partendo dai consumi indicati e dalla producibilita' stimata dell'impianto.",
        18 * mm,
        h - 88 * mm,
        165 * mm,
        6 * mm,
        size=11,
    )
    metric_box(18 * mm, h - 120 * mm, "RISPARMIO MEDIO ANNUO", eur(data["beneficio_annuo"]), "Risparmio + ritiro dedicato", 80 * mm)
    metric_box(108 * mm, h - 120 * mm, "RISPARMIO 10 ANNI", eur(risparmio_10), "Saldo cumulativo", 72 * mm)
    metric_box(18 * mm, h - 158 * mm, "IMPIANTO", f"{impianto['potenza_kwp']:.2f} kWp".replace(".", ","), f"{impianto['numero_pannelli']} x {impianto['potenza_pannello_wp']:.0f} W", 52 * mm)
    accumulo_kwh = float(impianto.get("accumulo_kwh") or impianto.get("batteria_kwh") or 0)
    metric_box(78 * mm, h - 158 * mm, "ACCUMULO", f"{accumulo_kwh:.0f} kWh", "Batteria installata", 52 * mm)
    metric_box(138 * mm, h - 158 * mm, "RIENTRO", f"Anno {be}", "Pareggio investimento", 52 * mm)
    metric_box(18 * mm, h - 196 * mm, "CONSUMO ANNUO CASA", kwh(consumi_annui), source_note(consumi_annui_fonte), 52 * mm)
    metric_box(78 * mm, h - 196 * mm, "PRODUZIONE", kwh(data["produzione_annua"]), "Stima PVGIS/fallback", 52 * mm)
    metric_box(138 * mm, h - 196 * mm, "COPERTURA", f"{copertura:.0f}%", "Produzione su consumi", 52 * mm)
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(18 * mm, h - 232 * mm, "Una soluzione pensata per il tuo futuro energetico")
    c.setFont("Helvetica", 10)
    draw_wrapped(
        f"Con i consumi rilevati e l'orientamento reale del tetto, questo impianto puo' coprire circa il {autonomia:.0f}% del fabbisogno elettrico dell'abitazione tramite energia autoconsumata.",
        18 * mm,
        h - 244 * mm,
        165 * mm,
    )
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(18 * mm, h - 265 * mm, "Fonti dati utilizzate")
    c.setFont("Helvetica", 8)
    y_fonti = h - 271 * mm
    for fonte_line in [
        f"Consumo annuo: {consumi_annui_fonte}",
        f"Consumo periodo: {consumo_mese_fonte}",
        f"Costo energia: {costo_energia_fonte}",
    ]:
        y_fonti = draw_wrapped(fonte_line, 18 * mm, y_fonti, 165 * mm, 4.2 * mm, size=8)
    c.showPage()

    # Page 2 - monthly production and consumption
    header("Produzione impianto da PVGIS", 2)
    section(
        "02 - PRODUZIONE E CONSUMI",
        ["Produzione stimata", "e fabbisogno mensile"],
        "Il confronto mostra quando l'impianto produce piu' del fabbisogno domestico e quando l'abitazione acquista energia dalla rete.",
    )
    rows_left = [["Mese", "Produzione", "% annuo"]]
    rows_right = [["Mese", "Produzione", "% annuo"]]
    labels = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    total = sum(monthly_values) or 1
    for i, (label, value) in enumerate(zip(labels, monthly_values)):
        row = [label, f"{value:,.0f}".replace(",", "."), f"{value / total * 100:.1f}%".replace(".", ",")]
        (rows_left if i < 6 else rows_right).append(row)
    simple_table(18 * mm, h - 92 * mm, rows_left, [22 * mm, 32 * mm, 26 * mm])
    simple_table(108 * mm, h - 92 * mm, rows_right, [22 * mm, 32 * mm, 26 * mm])
    consumi_mensili_letti = data.get("consumi_mensili") or []
    if len(consumi_mensili_letti) == 12 and all(float(value or 0) > 0 for value in consumi_mensili_letti):
        consumi_mensili = [float(value) for value in consumi_mensili_letti]
        fonte_mensile = data.get("consumi_mensili_fonte") or "Dettaglio mensile letto dalla bolletta"
        nota_consumi = f"I consumi mensili dell'abitazione usati nel confronto sono quelli mese per mese. Fonte: {fonte_mensile}."
    else:
        consumi_mensili = [consumi_annui / 12] * 12
        nota_consumi = f"I consumi mensili dell'abitazione sono stimati ripartendo su 12 mesi il consumo annuo. Fonte consumo annuo: {consumi_annui_fonte}. Se la bolletta non riporta un dettaglio mensile, questa ripartizione serve come confronto indicativo."
    chart = _dual_line_chart(monthly_values, consumi_mensili, labels, "Produzione vs consumi", "kWh/mese")
    c.drawImage(ImageReader(chart), 18 * mm, h - 230 * mm, width=172 * mm, height=70 * mm, mask="auto")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor(BLUE))
    c.drawString(18 * mm, h - 246 * mm, f"TOTALE ANNUO  {kwh(data['produzione_annua'])}  -  CONSUMI ANNUI  {kwh(consumi_annui)}")
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica", 8.5)
    draw_wrapped(
        nota_consumi,
        18 * mm,
        h - 257 * mm,
        165 * mm,
        4.5 * mm,
        size=8.5,
    )
    c.showPage()

    # Page 3 - investment
    header("Offerta economica e incentivi", 3)
    section(
        "03 - OFFERTA ECONOMICA",
        ["Investimento,", "contributi e agevolazioni."],
        "Il quadro economico mostra costo chiavi in mano, contributi, detrazione fiscale e capitale realmente esposto.",
    )
    costo_reale = data["esborso_netto"] - data["detrazione_totale"]
    waterfall = [
        ("Investimento", eur(data["costo_impianto"]), BLUE),
        (data["nome_contributo"], f"-{eur(data['contributo'])}", "#8E8E8E"),
        ("Esborso reale", eur(data["esborso_netto"]), BLUE),
        ("Detrazione fiscale", f"-{eur(data['detrazione_totale'])}", "#8E8E8E"),
        ("Costo netto finale", eur(costo_reale), GOLD),
    ]
    x = 18 * mm
    y = h - 96 * mm
    for label, value, color in waterfall:
        c.setFillColor(colors.HexColor(color))
        c.roundRect(x, y - 22 * mm, 31 * mm, 22 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x + 15.5 * mm, y - 7 * mm, label[:20])
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + 15.5 * mm, y - 16 * mm, value)
        if label != "Costo netto finale":
            c.setFillColor(colors.HexColor("#777777"))
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(x + 36 * mm, y - 13 * mm, ">")
        x += 39 * mm
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(18 * mm, h - 142 * mm, "Quando arrivano contributo e detrazione")
    c.setFont("Helvetica", 9.5)
    y = draw_wrapped(
        "Il contributo regionale viene erogato successivamente alla conclusione dei lavori e alla presentazione della pratica. La detrazione fiscale viene recuperata in quote annuali tramite dichiarazione dei redditi.",
        18 * mm,
        h - 154 * mm,
        165 * mm,
        size=9.5,
    )
    c.setFont("Helvetica-Bold", 11)
    y -= 4 * mm
    c.drawString(18 * mm, y, "In pratica")
    c.setFont("Helvetica", 10)
    draw_wrapped(
        f"A fronte di un investimento iniziale di {eur(data['costo_impianto'])}, il costo netto finale dell'impianto si riduce a circa {eur(costo_reale)} grazie agli incentivi disponibili.",
        18 * mm,
        y - 8 * mm,
        165 * mm,
        size=10,
    )
    c.setFont("Helvetica-Bold", 13)
    c.drawString(18 * mm, h - 210 * mm, "Offerta FOTOVOLTAICO")
    c.setFont("Helvetica", 10)
    y = draw_wrapped(
        "La soluzione e' pensata per chi desidera un impianto fotovoltaico completo, protetto e seguito nel tempo, senza costi imprevisti.",
        18 * mm,
        h - 222 * mm,
        165 * mm,
    )
    for line in ["desidera eliminare ogni incertezza futura", "non vuole costi imprevisti", "cerca un partner affidabile nel tempo"]:
        c.drawString(23 * mm, y - 3 * mm, f"- {line}")
        y -= 7 * mm
    c.showPage()

    # Page 4 - before / after
    header("Prima e dopo", 4)
    section(
        "04 - PRIMA E DOPO",
        ["Bolletta oggi", "e beneficio domani"],
        "Questa pagina traduce i numeri tecnici nel risultato piu' immediato: quanto cambia la bolletta annuale.",
    )
    metric_box(18 * mm, h - 102 * mm, "OGGI - BOLLETTA ANNUA", eur(data["spesa_annua_stimata"]), "Energia acquistata dalla rete", 74 * mm)
    metric_box(102 * mm, h - 102 * mm, "DOMANI - BOLLETTA RESIDUA", eur(bolletta_residua), "Quote fisse e consumi residui", 74 * mm)
    metric_box(18 * mm, h - 142 * mm, "RISPARMIO IN BOLLETTA", eur(risparmio_autoconsumo), "Energia autoconsumata", 52 * mm)
    metric_box(78 * mm, h - 142 * mm, "RICAVO ENERGIA IMMESSA", eur(ricavo_energia), "Ritiro dedicato", 52 * mm)
    metric_box(138 * mm, h - 142 * mm, "BENEFICIO TOTALE", eur(data["beneficio_annuo"]), "Anno 1 stimato", 52 * mm)
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica", 9)
    draw_wrapped(
        "La bolletta residua non viene stimata pari a zero: restano normalmente quote fisse, oneri e possibili prelievi dalla rete nei periodi in cui produzione e consumi non coincidono.",
        18 * mm,
        h - 182 * mm,
        165 * mm,
        4.8 * mm,
        size=9,
    )
    draw_wrapped(
        f"Costo energia utilizzato: {data.get('costo_energia', 0):.3f} EUR/kWh - Fonte: {costo_energia_fonte}",
        18 * mm,
        h - 202 * mm,
        165 * mm,
        4.2 * mm,
        size=8.5,
    )
    draw_wrapped(
        f"Autoconsumo utilizzato: {float(data.get('autoconsumo_pct') or 0):.1f}% ({kwh(autoconsumo_kwh)}) - Fonte: {autoconsumo_fonte}",
        18 * mm,
        h - 213 * mm,
        165 * mm,
        4.2 * mm,
        size=8.5,
    )
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(18 * mm, h - 244 * mm, 172 * mm, 36 * mm, 5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(26 * mm, h - 224 * mm, "Il fotovoltaico trasforma una spesa ricorrente")
    c.drawString(26 * mm, h - 235 * mm, "in energia autoprodotta e valore nel tempo.")
    c.showPage()

    # Page 4 - cumulative return
    header("Ritorno economico", 5)
    section(
        "05 - PROSPETTO ECONOMICO",
        ["Rientro dell'investimento", "nel tempo"],
        "Il grafico mostra quando l'investimento torna positivo grazie a risparmio in bolletta, ritiro dedicato e detrazioni.",
    )
    chart = _bar_chart(list(df["Saldo cumulativo (EUR)"]), list(df["Anno"]), "Ritorno economico impianto", "Saldo cumulativo")
    c.drawImage(ImageReader(chart), 18 * mm, h - 164 * mm, width=172 * mm, height=72 * mm, mask="auto")
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(18 * mm, h - 194 * mm, 172 * mm, 20 * mm, 4 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(24 * mm, h - 182 * mm, f"Dopo circa {be} anni l'impianto si e' ripagato.")
    c.setFont("Helvetica", 9)
    c.drawString(24 * mm, h - 189 * mm, "Da quel momento il risparmio generato rappresenta beneficio economico netto.")
    rows = [["Anno", "Saldo cumulativo"]]
    for anno in [5, 10, 20, 30]:
        subset = df[df["Anno"] == anno]
        if not subset.empty:
            rows.append([str(anno), eur(float(subset.iloc[0]["Saldo cumulativo (EUR)"]))])
    simple_table(18 * mm, h - 226 * mm, rows, [28 * mm, 54 * mm], row_h=9 * mm)
    metric_box(112 * mm, h - 226 * mm, "PAREGGIO INVESTIMENTO", f"Anno {be}", "Quando il saldo torna positivo", 70 * mm)
    c.showPage()

    # Page 6 - annual benefits
    header("Benefici annui", 6)
    section(
        "06 - ISTOGRAMMA BENEFICI",
        ["Da dove arriva", "il beneficio anno per anno"],
        "L'istogramma mostra l'evoluzione del beneficio negli anni. La tabella sotto riporta solo la composizione del primo anno.",
    )
    chart = _benefits_chart(df)
    c.drawImage(ImageReader(chart), 18 * mm, h - 150 * mm, width=172 * mm, height=60 * mm, mask="auto")
    rows = [
        ["Componente beneficio - anno 1", "Importo anno 1"],
        ["Risparmio da autoconsumo", eur(risparmio_autoconsumo)],
        ["Ritiro dedicato energia immessa", eur(ricavo_energia)],
        ["Beneficio totale primo anno", eur(data["beneficio_annuo"])],
    ]
    simple_table(18 * mm, h - 186 * mm, rows, [96 * mm, 54 * mm], row_h=8 * mm)
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(18 * mm, h - 232 * mm, "Protezione dall'aumento dell'energia")
    c.setFont("Helvetica", 9.5)
    y = h - 244 * mm
    aumento_energia = float(data.get("aumento_energia_pct") or 0)
    aumento_energia_testo = f"{aumento_energia:.1f}".replace(".", ",")
    for line in [
        f"La tabella indica il beneficio stimato al primo anno. Negli anni successivi il risparmio in bolletta cresce per effetto dell'aumento del costo energia impostato nel calcolo: {aumento_energia_testo}% annuo.",
        "Per questo il grafico e' piu' importante del singolo valore iniziale: mostra come il vantaggio economico evolve anno dopo anno.",
    ]:
        y = draw_wrapped(line, 18 * mm, y, 165 * mm, 5 * mm, size=9.5)
        y -= 2 * mm
    c.showPage()

    # Page 7 - environment and Climaservice
    header("Benefici ambientali e Climaservice", 7)
    section(
        "07 - VALORE AGGIUNTO",
        ["Benefici ambientali", "e perche' Climaservice"],
        "Il valore dell'impianto non e' solo economico: riduce emissioni e viene seguito da un partner locale.",
    )
    metric_box(18 * mm, h - 108 * mm, "CO2 EVITATA OGNI ANNO", f"{co2_kg/1000:.1f} t", "Stima su produzione annua", 52 * mm)
    metric_box(78 * mm, h - 108 * mm, "ALBERI EQUIVALENTI", f"{alberi:.0f}", "Assorbimento annuo stimato", 52 * mm)
    metric_box(138 * mm, h - 108 * mm, "KM AUTO EQUIVALENTI", f"{km_auto:,.0f}".replace(",", "."), "Emissioni evitate", 52 * mm)
    c.setFillColor(colors.HexColor(DARK))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(18 * mm, h - 150 * mm, "Perche' scegliere Climaservice")
    c.setFont("Helvetica", 10)
    y = h - 164 * mm
    for line in [
        "Azienda locale presente sul territorio.",
        "Oltre 13 anni di attivita' nell'efficienza energetica.",
        "Oltre 1.000 impianti realizzati.",
        "Assistenza interna, senza call center.",
        "Pratiche incentivi, distributore e GSE comprese.",
        "Monitoraggio, manutenzione e supporto post vendita.",
    ]:
        c.setFillColor(colors.HexColor(BLUE))
        c.circle(21 * mm, y + 1 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(DARK))
        c.drawString(26 * mm, y, line)
        y -= 9 * mm
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(18 * mm, h - 250 * mm, 172 * mm, 24 * mm, 4 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(w / 2, h - 241 * mm, "Un unico referente per analisi, progettazione, pratiche, installazione e assistenza.")
    c.showPage()

    c.save()
    buffer.seek(0)
    return buffer


def _monthly_values(values, annual):
    if values and len(values) == 12:
        return [float(v or 0) for v in values]
    seasonal = [0.052, 0.062, 0.088, 0.097, 0.106, 0.112, 0.121, 0.110, 0.089, 0.069, 0.047, 0.047]
    scale = annual / sum(seasonal)
    return [v * scale for v in seasonal]


def _font(size=22, bold=False):
    for candidate in [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _chart_canvas(title, subtitle):
    image = Image.new("RGB", (1400, 620), "white")
    draw = ImageDraw.Draw(image)
    draw.text((48, 28), title, fill=BLUE, font=_font(34, True))
    draw.text((48, 76), subtitle, fill="#555555", font=_font(19))
    return image, draw


def _save_image(image):
    out = BytesIO()
    image.save(out, format="PNG")
    out.seek(0)
    return out


def _scale(value, min_v, max_v, top, bottom):
    if max_v == min_v:
        return (top + bottom) / 2
    return bottom - ((value - min_v) / (max_v - min_v)) * (bottom - top)


def _grid(draw, left, top, right, bottom, min_v, max_v):
    axis_font = _font(16)
    for i in range(5):
        y = top + i * (bottom - top) / 4
        draw.line((left, y, right, y), fill="#E6E6E6", width=2)
        value = max_v - i * (max_v - min_v) / 4
        draw.text((28, y - 10), f"{value:,.0f}".replace(",", "."), fill="#666666", font=axis_font)
    draw.line((left, top, left, bottom), fill="#777777", width=2)
    draw.line((left, bottom, right, bottom), fill="#777777", width=2)


def _line_chart(values, labels, title, subtitle):
    image, draw = _chart_canvas(title, subtitle)
    left, top, right, bottom = 105, 135, 1345, 520
    min_v, max_v = 0, max(values) * 1.15
    _grid(draw, left, top, right, bottom, min_v, max_v)
    step = (right - left) / (len(values) - 1)
    points = [(left + i * step, _scale(v, min_v, max_v, top, bottom)) for i, v in enumerate(values)]
    draw.line(points, fill=GOLD, width=7)
    for x, y in points:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=GOLD, outline="#8A6B16", width=2)
    for i, label in enumerate(labels):
        draw.text((left + i * step - 18, bottom + 18), label, fill="#555555", font=_font(16))
    return _save_image(image)


def _dual_line_chart(production, consumption, labels, title, subtitle):
    image, draw = _chart_canvas(title, subtitle)
    left, top, right, bottom = 105, 135, 1345, 520
    max_v = max(max(production), max(consumption)) * 1.15
    _grid(draw, left, top, right, bottom, 0, max_v)
    step = (right - left) / (len(labels) - 1)
    prod_points = [(left + i * step, _scale(v, 0, max_v, top, bottom)) for i, v in enumerate(production)]
    cons_points = [(left + i * step, _scale(v, 0, max_v, top, bottom)) for i, v in enumerate(consumption)]
    draw.line(prod_points, fill=GOLD, width=7)
    draw.line(cons_points, fill=BLUE, width=6)
    for x, y in prod_points:
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=GOLD, outline="#8A6B16", width=2)
    for x, y in cons_points:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=BLUE, outline="#0E2442", width=2)
    for i, label in enumerate(labels):
        draw.text((left + i * step - 18, bottom + 18), label, fill="#555555", font=_font(16))
    draw.rectangle((1000, 70, 1022, 88), fill=GOLD)
    draw.text((1032, 66), "Produzione FV", fill="#333333", font=_font(18))
    draw.rectangle((1000, 100, 1022, 118), fill=BLUE)
    draw.text((1032, 96), "Consumi abitazione", fill="#333333", font=_font(18))
    return _save_image(image)


def _bar_chart(values, labels, title, subtitle):
    image, draw = _chart_canvas(title, subtitle)
    left, top, right, bottom = 105, 135, 1345, 520
    min_v, max_v = min(min(values), 0), max(max(values), 0)
    pad = max((max_v - min_v) * 0.12, 1)
    min_v -= pad
    max_v += pad
    _grid(draw, left, top, right, bottom, min_v, max_v)
    zero_y = _scale(0, min_v, max_v, top, bottom)
    draw.line((left, zero_y, right, zero_y), fill="#777777", width=3)
    step = (right - left) / len(values)
    bar_w = step * 0.72
    for value, label, idx in zip(values, labels, range(len(values))):
        x0 = left + idx * step + (step - bar_w) / 2
        x1 = x0 + bar_w
        y = _scale(value, min_v, max_v, top, bottom)
        draw.rectangle((x0, min(y, zero_y), x1, max(y, zero_y)), fill=BLUE if value >= 0 else "#9A9A9A")
        if int(label) % 5 == 0 or int(label) in (0, 1, 30):
            draw.text((x0 - 2, bottom + 18), str(int(label)), fill="#555555", font=_font(15))
    return _save_image(image)


def _benefits_chart(df):
    image, draw = _chart_canvas("Benefici annui", "Risparmio, ritiro dedicato e detrazione")
    left, top, right, bottom = 105, 135, 1345, 520
    years = list(range(1, min(31, int(df["Anno"].max()) + 1)))
    rows = [df[df["Anno"] == y].iloc[0] for y in years]
    totals = [
        float(r["Risparmio (EUR)"]) + float(r["Ritiro dedicato (EUR)"]) + float(r["Detrazione (EUR)"])
        for r in rows
    ]
    min_v, max_v = 0, max(totals) * 1.15
    _grid(draw, left, top, right, bottom, min_v, max_v)
    step = (right - left) / len(rows)
    bar_w = step * 0.68
    colors_ = ["#17365D", "#C6A23A", "#8E8E8E"]
    for idx, row in enumerate(rows):
        x0 = left + idx * step + (step - bar_w) / 2
        x1 = x0 + bar_w
        base = bottom
        for value, col in zip([row["Risparmio (EUR)"], row["Ritiro dedicato (EUR)"], row["Detrazione (EUR)"]], colors_):
            y = _scale(float(value), min_v, max_v, top, bottom)
            height = bottom - y
            draw.rectangle((x0, base - height, x1, base), fill=col)
            base -= height
        year = int(row["Anno"])
        if year % 5 == 0 or year == 1:
            draw.text((x0 - 2, bottom + 18), str(year), fill="#555555", font=_font(15))
    draw.rectangle((1050, 80, 1070, 96), fill="#17365D")
    draw.text((1078, 78), "Autoconsumo", fill="#333333", font=_font(16))
    draw.rectangle((1050, 105, 1070, 121), fill="#C6A23A")
    draw.text((1078, 103), "Ritiro dedicato", fill="#333333", font=_font(16))
    draw.rectangle((1050, 130, 1070, 146), fill="#8E8E8E")
    draw.text((1078, 128), "Detrazione", fill="#333333", font=_font(16))
    return _save_image(image)
