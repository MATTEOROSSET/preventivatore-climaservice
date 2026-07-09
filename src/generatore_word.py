from datetime import date
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape, unescape

from PIL import Image, ImageDraw, ImageFont

from .utility_formattazione import euro, euro2, kwh


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}

for prefix, uri in NS.items():
    if prefix not in {"pr", "ct"}:
        ET.register_namespace(prefix, uri)

MONTHS_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def data_italiana(value=None):
    value = value or date.today()
    return f"{value.day} {MONTHS_IT[value.month - 1]} {value.year}"


def default_template_path(app_dir):
    app_dir = Path(app_dir)
    bundled_template = app_dir / "templates" / "PR_fotovoltaico Trina SAJ.docx"
    if bundled_template.exists():
        return bundled_template
    return app_dir.parent / "esempi di preventivi" / "PR_fotovoltaico Trina SAJ.docx"


def genera_preventivo_word(template_path, data, df, impianto, monthly_values=None, data_preventivo=None):
    template_path = Path(template_path)
    output = BytesIO()

    with ZipFile(template_path, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    document_xml = files["word/document.xml"].decode("utf-8")
    files["word/document.xml"] = _aggiorna_preventivo_xml(document_xml, data, impianto, data_preventivo).encode("utf-8")

    with ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for name, content in files.items():
            zout.writestr(name, content)

    output.seek(0)
    return output


def _aggiorna_preventivo_xml(xml, data, impianto, data_preventivo=None):
    cliente = _xml_text(data.get("cliente") or "Cliente")
    indirizzo = _xml_text(data.get("indirizzo") or "")
    localita = _xml_text(data.get("localita") or "")
    data_testo = _xml_text(data_italiana(data_preventivo))
    costo_reale = float(data.get("costo_impianto") or 0) - float(data.get("contributo") or 0) - float(data.get("detrazione_totale") or 0)
    contributo_label = _label_contributo(data)

    xml = _replace_visible_text(xml, "ZULIANI GIANNI", cliente)
    xml = _replace_visible_text(xml, "Via D", indirizzo)
    xml = _replace_visible_text(xml, "ivisione Julia, 1", "")
    xml = _replace_first(xml, "Spilimbergo", localita)
    xml = _replace_first(xml, "Spilimbergo", localita)
    xml = _replace_first(xml, " (PN)", "")
    xml = _replace_first(xml, " (PN)", "")
    xml = _replace_visible_text(xml, "28 maggio 2026", data_testo)

    xml = _replace_visible_text(xml, "6,51 kWp", _xml_text(f"{impianto['potenza_kwp']:.2f} kWp".replace(".", ",")))
    xml = _replace_visible_text(xml, "TRINA SOLAR", _xml_text(impianto["tipo_pannelli"]))
    xml = _replace_visible_text(xml, "TSM-NEG9R.28", _xml_text(impianto["modello_pannelli"]))
    xml = _replace_visible_text(xml, "nr 14 moduli", _xml_text(f"nr {impianto['numero_pannelli']} moduli"))
    xml = _replace_visible_text(xml, "14 moduli", _xml_text(f"{impianto['numero_pannelli']} moduli"))
    xml = _replace_visible_text(xml, "465 Wp", _xml_text(f"{impianto['potenza_pannello_wp']:.0f} Wp"))
    xml = _replace_visible_text(xml, "Fornitura e posa inverter monofase ibrido SAJ", _xml_text(f"Fornitura e posa inverter {impianto['inverter']}."))
    xml = _replace_visible_text(xml, "SAJ", _xml_text(impianto["inverter"]), count=1)
    xml = _replace_visible_text(xml, "SAJI Mod. HS2", _xml_text(impianto["batteria"]))
    xml = _replace_visible_text(xml, "SAJ Mod. HS2", _xml_text(impianto["batteria"]))
    xml = _replace_visible_text(xml, "SAJ", _xml_text(impianto["batteria"]), count=1)
    xml = _replace_visible_text(xml, "10 kWh", _xml_text(f"{impianto['accumulo_kwh']:.0f} kWh"))
    descrizione_moduli = impianto.get("descrizione_moduli") or ""
    if descrizione_moduli:
        vecchia_descrizione_moduli = (
            f"Fornitura e posa nr {impianto['numero_pannelli']} moduli fotovoltaici {impianto['tipo_pannelli']} "
            f"modello {impianto['modello_pannelli']}  moduli a doppio vetro, celle con tecnologia TOPCon Ultra N-type "
            "per elevate prestazioni e affidabilita, elevata efficienza dei moduli, fino a 23,5%, tolleranza di potenza "
            "solo positiva -0/+5W. Costruiti utilizzo di materiali di qualita elevata per una protezione ottimale contro "
            "l'effetto Hot-Spot e la degradazione del modulo, due vetri con rivestimento selettivo antiriflesso per "
            f"rendimenti solari ottimali al silicio monocristallino con potenza pari a {impianto['potenza_pannello_wp']:.0f} Wp"
        )
        nuova_descrizione_moduli = (
            f"Fornitura e posa nr {impianto['numero_pannelli']} moduli fotovoltaici {impianto['tipo_pannelli']} "
            f"modello {impianto['modello_pannelli']}, potenza unitaria {impianto['potenza_pannello_wp']:.0f} Wp. "
            f"{descrizione_moduli}"
        )
        xml = _replace_visible_text(xml, vecchia_descrizione_moduli, _xml_text(nuova_descrizione_moduli))
    descrizione_batteria = impianto.get("descrizione_batteria") or ""
    if descrizione_batteria:
        nuova_descrizione_batteria = (
            f"Fornitura e posa batterie di accumulo {impianto['batteria']}, capacita di accumulo "
            f"{impianto['accumulo_kwh']:.0f} kWh. {descrizione_batteria}"
        )
        xml = _replace_visible_text(
            xml,
            f"Fornitura e posa batterie di accumulo {impianto['batteria']}, capacità di accumulo {impianto['accumulo_kwh']:.0f} kWh",
            _xml_text(nuova_descrizione_batteria),
        )

    xml = _replace_visible_text(xml, "\u20ac 14.200,00", _xml_text(euro2(data.get("costo_impianto") or 0)))
    xml = _replace_visible_text(xml, "- \u20ac 5.680,00", _xml_text(f"- {euro2(data.get('contributo') or 0)}"))
    xml = _replace_visible_text(xml, "- \u20ac 7.100,00", _xml_text(f"- {euro2(data.get('detrazione_totale') or 0)}"))
    xml = _replace_visible_text(xml, "\u20ac 1.420,00", _xml_text(euro2(max(costo_reale, 0))))
    xml = _replace_visible_text(xml, "Bonus FVG 40% a fondo perduto", _xml_text(contributo_label))
    xml = _replace_visible_text(
        xml,
        "Detrazione fiscale 50% (10 anni)",
        _xml_text(f"Detrazione fiscale {float(data.get('detrazione_pct') or 0):.0f}% ({int(data.get('anni_detrazione') or 10)} anni)"),
    )
    return xml


def _label_contributo(data):
    nome = data.get("nome_contributo") or "Contributo"
    pct = float(data.get("contributo_pct") or 0)
    if pct > 0:
        return f"{nome} {pct:.0f}% a fondo perduto"
    return nome


def _replace_visible_text(xml, old, new, count=None):
    remaining = count
    while remaining is None or remaining > 0:
        updated = _replace_visible_text_once(xml, old, new)
        if updated == xml:
            return xml
        xml = updated
        if remaining is not None:
            remaining -= 1
    return xml


def _replace_visible_text_once(xml, old, new):
    text_nodes = list(_iter_text_nodes(xml))
    visible = "".join(node["text"] for node in text_nodes)
    start = visible.find(unescape(str(old)))
    if start < 0:
        return xml
    end = start + len(unescape(str(old)))

    cursor = 0
    start_node = end_node = None
    start_offset = end_offset = 0
    for idx, node in enumerate(text_nodes):
        next_cursor = cursor + len(node["text"])
        if start_node is None and cursor <= start < next_cursor:
            start_node = idx
            start_offset = start - cursor
        if cursor < end <= next_cursor:
            end_node = idx
            end_offset = end - cursor
            break
        cursor = next_cursor
    if start_node is None or end_node is None:
        return xml

    replacement = unescape(str(new))
    if start_node == end_node:
        node = text_nodes[start_node]
        node["text"] = node["text"][:start_offset] + replacement + node["text"][end_offset:]
    else:
        first = text_nodes[start_node]
        last = text_nodes[end_node]
        first["text"] = first["text"][:start_offset] + replacement
        for idx in range(start_node + 1, end_node):
            text_nodes[idx]["text"] = ""
        last["text"] = last["text"][end_offset:]

    parts = []
    cursor = 0
    for node in text_nodes:
        parts.append(xml[cursor:node["content_start"]])
        parts.append(_xml_text(node["text"]))
        cursor = node["content_end"]
    parts.append(xml[cursor:])
    return "".join(parts)


def _iter_text_nodes(xml):
    for match in re.finditer(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", xml, flags=re.S):
        yield {
            "content_start": match.start(2),
            "content_end": match.end(2),
            "text": unescape(match.group(2)),
        }


def _replace_first(text, old, new):
    return text.replace(old, new, 1)


def _xml_text(value):
    return escape(str(value))


def genera_analisi_word(data, df, impianto, monthly_values=None, data_preventivo=None):
    document = _blank_document()
    body = document.find("w:body", NS)

    body.extend([
        _paragraph("Analisi rendimento impianto fotovoltaico", bold=True, size="34", color="17365D"),
        _paragraph(f"Cliente: {data.get('cliente', '')}", bold=True, size="24"),
        _paragraph(f"Data: {data_italiana(data_preventivo)}", size="21"),
        _paragraph(""),
        _paragraph(
            "Il presente allegato riporta la simulazione energetica ed economica dell'impianto proposto, "
            "calcolata con i dati inseriti nel preventivatore Climaservice.",
            size="21",
        ),
        _paragraph("Dati impianto", bold=True, size="26", color="17365D"),
        _build_table([
            ["Parametro", "Valore"],
            ["Potenza impianto", f"{impianto['potenza_kwp']:.2f} kWp".replace(".", ",")],
            ["Moduli", f"{impianto['numero_pannelli']} x {impianto['potenza_pannello_wp']:.0f} Wp - {impianto['tipo_pannelli']}"],
            ["Inverter", impianto["inverter"]],
            ["Accumulo", f"{impianto['accumulo_kwh']:.0f} kWh - {impianto['batteria']}"],
            ["Produzione annua stimata", kwh(data["produzione_annua"])],
        ], header=True),
        _paragraph("Fonti dati utilizzate", bold=True, size="26", color="17365D"),
        _build_table([
            ["Dato", "Valore", "Fonte"],
            ["Consumo periodo bolletta", kwh(data.get("consumo_mese") or 0), data.get("consumo_mese_fonte") or "Non rilevato"],
            ["Consumo annuo", kwh(data.get("consumi_annui") or 0), data.get("consumi_annui_fonte") or "Non rilevato"],
            ["Costo energia", f"{float(data.get('costo_energia') or 0):.3f} EUR/kWh", data.get("costo_energia_fonte") or "Non rilevato"],
            ["Autoconsumo", f"{float(data.get('autoconsumo_pct') or 0):.1f}% - {kwh(data.get('autoconsumo_kwh') or 0)}", data.get("autoconsumo_fonte") or "Non rilevato"],
        ], header=True),
        _paragraph("Sintesi economica", bold=True, size="26", color="17365D"),
        _kpi_table(data),
        _paragraph("Grafici", bold=True, size="26", color="17365D"),
        _paragraph("Produzione mensile stimata", bold=True, size="22"),
    ])

    files = _minimal_docx_files(document)
    rels = ET.fromstring(files["word/_rels/document.xml.rels"])
    content_types = ET.fromstring(files["[Content_Types].xml"])
    image1_rid = _add_image_part(files, rels, "produzione_mensile.png", _make_production_chart(monthly_values, data["produzione_annua"]).getvalue())
    image2_rid = _add_image_part(files, rels, "ritorno_economico.png", _make_cashflow_chart(df).getvalue())
    _ensure_png_content_type(content_types)

    body.append(_image_paragraph(image1_rid, 5842000, 2580000))
    body.append(_paragraph("Ritorno economico impianto", bold=True, size="22"))
    body.append(_image_paragraph(image2_rid, 5842000, 2580000))
    body.append(_paragraph("Prospetto ritorno economico", bold=True, size="26", color="17365D"))
    body.append(_cashflow_table(df))
    body.append(_paragraph(""))
    body.append(_paragraph(
        "Nota: i valori sono stime basate sui parametri inseriti e possono variare in funzione dei consumi reali, "
        "dell'irraggiamento, del profilo di autoconsumo e delle condizioni economiche applicate.",
        size="18",
    ))

    files["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    files["word/_rels/document.xml.rels"] = ET.tostring(rels, encoding="utf-8", xml_declaration=True)
    files["[Content_Types].xml"] = ET.tostring(content_types, encoding="utf-8", xml_declaration=True)

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for name, content in files.items():
            zout.writestr(name, content)
    output.seek(0)
    return output


def converti_word_in_pdf(docx_bytes, work_dir=None):
    work_dir = Path(work_dir or Path.cwd())
    tmp_root = work_dir / "tmp_pdf"
    tmp_root.mkdir(exist_ok=True)
    tmp_dir = tmp_root / f"preventivo_pdf_{uuid4().hex}"
    tmp_dir.mkdir(exist_ok=True)
    docx_path = tmp_dir / "preventivo.docx"
    pdf_path = tmp_dir / "preventivo.pdf"
    docx_path.write_bytes(docx_bytes)

    errors = []
    if _convert_with_word_vbs(docx_path, pdf_path, errors):
        return pdf_path.read_bytes()
    if _convert_with_libreoffice(docx_path, pdf_path, tmp_dir, errors):
        return pdf_path.read_bytes()
    raise RuntimeError("Conversione PDF non riuscita. " + " | ".join(errors))


def _convert_with_word_vbs(docx_path, pdf_path, errors):
    script_path = docx_path.parent / "convert_word_pdf.vbs"
    stdout_path = docx_path.parent / "convert_word_pdf.out.log"
    stderr_path = docx_path.parent / "convert_word_pdf.err.log"
    script = f'''Option Explicit
Dim word
Dim doc
On Error Resume Next
Set word = CreateObject("Word.Application")
If Err.Number <> 0 Then
  WScript.Echo "CreateObject failed: " & Err.Description
  WScript.Quit 1
End If
On Error GoTo 0
WScript.Echo "word-created"
word.Visible = False
word.DisplayAlerts = 0
Set doc = word.Documents.Open("{_vbs_path(docx_path)}", False, True, False)
WScript.Echo "doc-opened"
doc.ExportAsFixedFormat "{_vbs_path(pdf_path)}", 17
WScript.Echo "pdf-exported"
doc.Close False
word.Quit
WScript.Echo "done"
'''
    script_path.write_text(script, encoding="ascii")
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
            result = subprocess.run(
                ["cscript", "//nologo", str(script_path)],
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                timeout=150,
            )
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="ignore") if stdout_path.exists() else ""
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="ignore") if stderr_path.exists() else ""
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        errors.append((stderr_text or stdout_text or "Microsoft Word via cscript non ha prodotto il PDF").strip())
    except Exception as exc:
        errors.append(f"Microsoft Word via cscript: {exc}")
    return False


def _vbs_path(path):
    return str(path).replace('"', '""')


def _convert_with_word_com(docx_path, pdf_path, errors):
    log_path = docx_path.parent / "word_conversion.log"
    script = f"""
$ErrorActionPreference = 'Stop'
$log = '{str(log_path)}'
"start" | Out-File -FilePath $log -Encoding UTF8
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
try {{
    "word-created" | Out-File -FilePath $log -Encoding UTF8 -Append
    $doc = $word.Documents.OpenNoRepairDialog('{str(docx_path)}', $false, $true, $false, '', '', $false, '', '', 0, 0, $false, $false, 0, $true)
    "doc-opened" | Out-File -FilePath $log -Encoding UTF8 -Append
    $doc.ExportAsFixedFormat('{str(pdf_path)}', 17, $false, 0, 0, 1, 1, 0, $true, $true, 0, $true, $true, $false)
    "pdf-exported" | Out-File -FilePath $log -Encoding UTF8 -Append
    $doc.Close()
}} finally {{
    $word.Quit()
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        errors.append((result.stderr or result.stdout or f"Microsoft Word non disponibile. Log: {log_text}").strip())
    except Exception as exc:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        errors.append(f"Microsoft Word: {exc}. Log: {log_text}")
    return False


def _convert_with_libreoffice(docx_path, pdf_path, tmp_dir, errors):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        for candidate in [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]:
            if Path(candidate).exists():
                soffice = candidate
                break
    if not soffice:
        errors.append("LibreOffice non disponibile")
        return False
    env = os.environ.copy()
    env["TEMP"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    try:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmp_dir), str(docx_path)],
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        errors.append((result.stderr or result.stdout or "LibreOffice non ha prodotto il PDF").strip())
    except Exception as exc:
        errors.append(f"LibreOffice: {exc}")
    return False


def _qn(tag):
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def _blank_document():
    document = ET.Element(_qn("w:document"))
    ET.SubElement(document, _qn("w:body"))
    return document


def _append_section_properties(document):
    body = document.find("w:body", NS)
    for child in list(body):
        if child.tag == _qn("w:sectPr"):
            body.remove(child)
    sect_pr = ET.SubElement(body, _qn("w:sectPr"))
    ET.SubElement(sect_pr, _qn("w:pgSz"), {_qn("w:w"): "11906", _qn("w:h"): "16838"})
    ET.SubElement(sect_pr, _qn("w:pgMar"), {
        _qn("w:top"): "1134",
        _qn("w:right"): "1134",
        _qn("w:bottom"): "1134",
        _qn("w:left"): "1134",
        _qn("w:header"): "708",
        _qn("w:footer"): "708",
        _qn("w:gutter"): "0",
    })


def _minimal_docx_files(document):
    _append_section_properties(document)
    return {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ).encode("utf-8"),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            '</Relationships>'
        ).encode("utf-8"),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        ).encode("utf-8"),
        "word/document.xml": ET.tostring(document, encoding="utf-8", xml_declaration=True),
    }


def _text_of(element):
    return "".join(t.text or "" for t in element.findall(".//w:t", NS))


def _set_paragraph_text(paragraph, text, bold=False, size="20", color=None):
    if _replace_text_preserve_format(paragraph, text):
        return
    paragraph.append(_run(text, bold=bold, size=size, color=color))


def _replace_date(document, replacement):
    for paragraph in document.findall(".//w:p", NS):
        if _text_of(paragraph).strip().startswith("Spilimbergo,"):
            _rewrite_paragraph_text(paragraph, replacement, size="20")
            return


def _rewrite_paragraph_text(paragraph, text, bold=False, size="20", color=None):
    for child in list(paragraph):
        if child.tag != _qn("w:pPr"):
            paragraph.remove(child)
    paragraph.append(_run(text, bold=bold, size=size, color=color))


def _replace_cover_customer(document, data):
    for paragraph in document.findall(".//w:p", NS):
        nodes = paragraph.findall(".//w:t", NS)
        values = [node.text or "" for node in nodes]
        if "ZULIANI GIANNI" not in "".join(values):
            continue
        cliente = data.get("cliente") or "Cliente"
        indirizzo = data.get("indirizzo") or ""
        localita = data.get("localita") or ""
        for base in (0, 6):
            if len(nodes) > base + 5 and (nodes[base].text or "").startswith("Spett.le"):
                nodes[base + 1].text = cliente
                nodes[base + 2].text = indirizzo
                nodes[base + 3].text = ""
                nodes[base + 4].text = localita
                nodes[base + 5].text = ""
        return


def _run(text, bold=False, size="20", color=None):
    run = ET.Element(_qn("w:r"))
    rpr = ET.SubElement(run, _qn("w:rPr"))
    ET.SubElement(rpr, _qn("w:rFonts"), {
        _qn("w:ascii"): "Arial",
        _qn("w:hAnsi"): "Arial",
        _qn("w:cs"): "Arial",
    })
    if bold:
        ET.SubElement(rpr, _qn("w:b"))
        ET.SubElement(rpr, _qn("w:bCs"))
    if color:
        ET.SubElement(rpr, _qn("w:color"), {_qn("w:val"): color})
    ET.SubElement(rpr, _qn("w:sz"), {_qn("w:val"): size})
    ET.SubElement(rpr, _qn("w:szCs"), {_qn("w:val"): size})
    t = ET.SubElement(run, _qn("w:t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = str(text)
    return run


def _paragraph(text="", bold=False, size="20", color=None, align=None):
    p = ET.Element(_qn("w:p"))
    if align:
        ppr = ET.SubElement(p, _qn("w:pPr"))
        ET.SubElement(ppr, _qn("w:jc"), {_qn("w:val"): align})
    p.append(_run(text, bold=bold, size=size, color=color))
    return p


def _cell_text(cell, text, bold=False):
    if _replace_text_preserve_format(cell, text):
        return
    cell.append(_paragraph(text, bold=bold, size="21"))


def _replace_text_preserve_format(element, text):
    text_nodes = element.findall(".//w:t", NS)
    if not text_nodes:
        return False
    text_nodes[0].text = str(text)
    for node in text_nodes[1:]:
        node.text = ""
    return True


def _table_rows(table):
    return [child for child in table if child.tag == _qn("w:tr")]


def _row_cells(row):
    return [child for child in row if child.tag == _qn("w:tc")]


def _aggiorna_descrizione_impianto(tables, impianto):
    if len(tables) > 3:
        valori = [
            ("Potenza nominale campo fotovoltaico", f"{impianto['potenza_kwp']:.2f} kWp".replace(".", ",")),
            ("Tipo di pannelli", impianto["tipo_pannelli"]),
            ("Inverter", impianto["inverter"]),
            ("Batterie di accumulo", impianto["batteria"]),
            ("Capacità di accumulo", f"{impianto['accumulo_kwh']:.0f} kWh"),
        ]
        _fill_two_col_table(tables[3], valori)

    if len(tables) > 4:
        descrizioni = [
            (
                "Moduli fotovoltaici",
                f"Fornitura e posa nr {impianto['numero_pannelli']} moduli fotovoltaici {impianto['tipo_pannelli']} "
                f"modello {impianto['modello_pannelli']}, potenza unitaria {impianto['potenza_pannello_wp']:.0f} Wp.",
            ),
            ("Inverter", f"Fornitura e posa inverter {impianto['inverter']}."),
            (
                "Batterie di accumulo",
                f"Fornitura e posa batterie di accumulo {impianto['batteria']}, capacità di accumulo "
                f"{impianto['accumulo_kwh']:.0f} kWh.",
            ),
            ("Monitoraggio", "Attivazione monitoraggio da app per controllo produzione, consumi e stato impianto."),
            ("Installazione", "Installazione chiavi in mano comprensiva di pratiche, collaudo e messa in esercizio."),
            (
                "Pratiche e documentazione",
                "Realizzazione progettazione impianto, sviluppo documentazione necessaria per la domanda di connessione "
                "alla rete di distribuzione e pratiche GSE, comprensive di predisposizione, presentazione e gestione "
                "della documentazione tecnico-amministrativa necessaria all'attivazione dei servizi di valorizzazione "
                "dell'energia immessa in rete.",
            ),
        ]
        if impianto.get("descrizione_moduli"):
            descrizioni[0] = (
                "Moduli fotovoltaici",
                f"Fornitura e posa nr {impianto['numero_pannelli']} moduli fotovoltaici {impianto['tipo_pannelli']} "
                f"modello {impianto['modello_pannelli']}, potenza unitaria {impianto['potenza_pannello_wp']:.0f} Wp. "
                f"{impianto['descrizione_moduli']}",
            )
        if impianto.get("descrizione_batteria"):
            descrizioni[2] = (
                "Batterie di accumulo",
                f"Fornitura e posa batterie di accumulo {impianto['batteria']}, capacita di accumulo "
                f"{impianto['accumulo_kwh']:.0f} kWh. {impianto['descrizione_batteria']}",
            )
        _fill_two_col_table(tables[4], descrizioni)


def _aggiorna_costi(tables, data):
    if len(tables) <= 6:
        return
    righe = [
        ("Costo dell'impianto chiavi in mano", euro2(data["costo_impianto"])),
        (data["nome_contributo"], f"- {euro2(data['contributo'])}"),
        (f"Detrazione fiscale {data['detrazione_pct']:.0f}% ({data['anni_detrazione']} anni)", f"- {euro2(data['detrazione_totale'])}"),
        ("Totale netto indicativo dopo contributo", euro2(data["esborso_netto"])),
    ]
    _fill_two_col_table(tables[6], righe)


def _fill_two_col_table(table, values):
    rows = _table_rows(table)
    for row, (label, value) in zip(rows, values):
        cells = _row_cells(row)
        if len(cells) >= 2:
            _cell_text(cells[0], label, bold=True)
            _cell_text(cells[1], value)


def _inserisci_analisi_economica(document, tables, data, df, prod_rid, cash_rid):
    body = document.find("w:body", NS)
    anchor = tables[6] if len(tables) > 6 else body[-1]
    insert_at = list(body).index(anchor) + 1

    blocks = [
        _paragraph(""),
        _paragraph(""),
        _paragraph("Analisi rendimento e ritorno economico", bold=True, size="28", color="000000"),
        _paragraph(
            "I prospetti seguenti sono calcolati con il preventivatore Climaservice sulla base dei consumi, "
            "della produzione stimata e dei parametri economici inseriti.",
            size="21",
        ),
        _kpi_table(data),
        _paragraph("Grafici di rendimento", bold=True, size="21", color="000000"),
        _image_paragraph(prod_rid, 5842000, 2580000),
        _image_paragraph(cash_rid, 5842000, 2580000),
        _paragraph("Prospetto ritorno economico", bold=True, size="21", color="000000"),
        _cashflow_table(df),
    ]
    for offset, block in enumerate(blocks):
        body.insert(insert_at + offset, block)


def _kpi_table(data):
    labels = ["Produzione annua", "Beneficio anno 1", "Pareggio stimato", "Beneficio 30 anni"]
    values = [kwh(data["produzione_annua"]), euro(data["beneficio_annuo"]), f"Anno {data['break_even']}", euro(data["beneficio_30"])]
    return _build_table([labels, values], header=True)


def _cashflow_table(df):
    anni = [0, 1, 5, 10, 15, 20, 25, 30]
    rows = [["Anno", "Produzione", "Risparmio", "Flusso di cassa", "Saldo cumulativo"]]
    for anno in anni:
        subset = df[df["Anno"] == anno]
        if subset.empty:
            continue
        row = subset.iloc[0]
        rows.append([
            str(int(row["Anno"])),
            kwh(row["Produzione (kWh)"]),
            euro(row["Risparmio (EUR)"]),
            euro(row["Flusso di cassa (EUR)"]),
            euro(row["Saldo cumulativo (EUR)"]),
        ])
    return _build_table(rows, header=True)


def _build_table(rows, header=False):
    tbl = ET.Element(_qn("w:tbl"))
    tbl_pr = ET.SubElement(tbl, _qn("w:tblPr"))
    ET.SubElement(tbl_pr, _qn("w:tblStyle"), {_qn("w:val"): "TableGrid"})
    ET.SubElement(tbl_pr, _qn("w:tblW"), {_qn("w:w"): "0", _qn("w:type"): "auto"})
    borders = ET.SubElement(tbl_pr, _qn("w:tblBorders"))
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        ET.SubElement(borders, _qn(f"w:{edge}"), {_qn("w:val"): "single", _qn("w:sz"): "4", _qn("w:space"): "0", _qn("w:color"): "D9D9D9"})

    for row_idx, row_values in enumerate(rows):
        tr = ET.SubElement(tbl, _qn("w:tr"))
        for value in row_values:
            tc = ET.SubElement(tr, _qn("w:tc"))
            tc_pr = ET.SubElement(tc, _qn("w:tcPr"))
            ET.SubElement(tc_pr, _qn("w:tcW"), {_qn("w:w"): "2200", _qn("w:type"): "dxa"})
            tc.append(_paragraph(str(value), bold=(header and row_idx == 0), size="19", color=("17365D" if header and row_idx == 0 else None), align="center"))
    return tbl


def _add_image_part(files, rels, filename, content):
    media_name = f"word/media/{filename}"
    counter = 1
    while media_name in files:
        stem, suffix = filename.rsplit(".", 1)
        media_name = f"word/media/{stem}_{counter}.{suffix}"
        counter += 1
    files[media_name] = content

    existing_ids = []
    for rel in rels:
        rid = rel.attrib.get("Id", "")
        if rid.startswith("rId"):
            try:
                existing_ids.append(int(rid[3:]))
            except ValueError:
                pass
    rid = f"rId{max(existing_ids or [0]) + 1}"
    rel = ET.SubElement(rels, f"{{{NS['pr']}}}Relationship")
    rel.set("Id", rid)
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    rel.set("Target", f"media/{Path(media_name).name}")
    return rid


def _ensure_png_content_type(content_types):
    for child in content_types:
        if child.tag.endswith("Default") and child.attrib.get("Extension") == "png":
            return
    default = ET.SubElement(content_types, f"{{{NS['ct']}}}Default")
    default.set("Extension", "png")
    default.set("ContentType", "image/png")


def _image_paragraph(rid, cx, cy):
    p = _paragraph("", align="center")
    run = p.find("w:r", NS)
    drawing = ET.SubElement(run, _qn("w:drawing"))
    inline = ET.SubElement(drawing, _qn("wp:inline"))
    ET.SubElement(inline, _qn("wp:extent"), {"cx": str(cx), "cy": str(cy)})
    ET.SubElement(inline, _qn("wp:docPr"), {"id": "1", "name": "Grafico"})
    graphic = ET.SubElement(inline, _qn("a:graphic"))
    graphic_data = ET.SubElement(graphic, _qn("a:graphicData"), {"uri": "http://schemas.openxmlformats.org/drawingml/2006/picture"})
    pic = ET.SubElement(graphic_data, _qn("pic:pic"))
    nv = ET.SubElement(pic, _qn("pic:nvPicPr"))
    ET.SubElement(nv, _qn("pic:cNvPr"), {"id": "0", "name": "chart.png"})
    ET.SubElement(nv, _qn("pic:cNvPicPr"))
    blip_fill = ET.SubElement(pic, _qn("pic:blipFill"))
    ET.SubElement(blip_fill, _qn("a:blip"), {_qn("r:embed"): rid})
    stretch = ET.SubElement(blip_fill, _qn("a:stretch"))
    ET.SubElement(stretch, _qn("a:fillRect"))
    sp_pr = ET.SubElement(pic, _qn("pic:spPr"))
    xfrm = ET.SubElement(sp_pr, _qn("a:xfrm"))
    ET.SubElement(xfrm, _qn("a:off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, _qn("a:ext"), {"cx": str(cx), "cy": str(cy)})
    prst = ET.SubElement(sp_pr, _qn("a:prstGeom"), {"prst": "rect"})
    ET.SubElement(prst, _qn("a:avLst"))
    return p


def _make_cashflow_chart(df):
    values = [float(v) for v in df["Saldo cumulativo (EUR)"]]
    labels = [int(v) for v in df["Anno"]]
    return _draw_bar_chart(values, labels, "Ritorno economico impianto", "Saldo cumulativo (EUR)")


def _make_production_chart(monthly_values, produzione_annua):
    labels = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    if not monthly_values or len(monthly_values) != 12:
        monthly_values = [produzione_annua / 12] * 12
    return _draw_line_chart([float(v) for v in monthly_values], labels, "Produzione mensile stimata", "kWh")


def _font(size=18, bold=False):
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _chart_canvas(title, y_label):
    width, height = 1400, 620
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((48, 30), title, fill="#17365D", font=_font(34, True))
    draw.text((48, 78), y_label, fill="#555555", font=_font(19))
    return image, draw, width, height


def _scale(value, min_v, max_v, top, bottom):
    if max_v == min_v:
        return (top + bottom) / 2
    return bottom - ((value - min_v) / (max_v - min_v)) * (bottom - top)


def _save_chart(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _draw_grid(draw, left, top, right, bottom, min_v, max_v):
    axis_font = _font(16)
    for i in range(5):
        y = top + i * (bottom - top) / 4
        draw.line((left, y, right, y), fill="#E6E6E6", width=2)
        value = max_v - i * (max_v - min_v) / 4
        draw.text((30, y - 10), f"{value:,.0f}".replace(",", "."), fill="#666666", font=axis_font)
    draw.line((left, top, left, bottom), fill="#777777", width=2)
    draw.line((left, bottom, right, bottom), fill="#777777", width=2)


def _draw_line_chart(values, labels, title, y_label):
    image, draw, width, height = _chart_canvas(title, y_label)
    left, top, right, bottom = 100, 135, width - 50, height - 90
    min_v, max_v = 0, max(values) * 1.15
    _draw_grid(draw, left, top, right, bottom, min_v, max_v)
    step = (right - left) / (len(values) - 1)
    points = [(left + i * step, _scale(v, min_v, max_v, top, bottom)) for i, v in enumerate(values)]
    draw.line(points, fill="#C6A23A", width=6)
    for x, y in points:
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#C6A23A", outline="#8A6B16", width=2)
    axis_font = _font(16)
    for i, label in enumerate(labels):
        x = left + i * step
        draw.text((x - 18, bottom + 18), str(label), fill="#555555", font=axis_font)
    return _save_chart(image)


def _draw_bar_chart(values, labels, title, y_label):
    image, draw, width, height = _chart_canvas(title, y_label)
    left, top, right, bottom = 100, 135, width - 50, height - 90
    min_v, max_v = min(min(values), 0), max(max(values), 0)
    margin = max((max_v - min_v) * 0.12, 1)
    min_v -= margin
    max_v += margin
    _draw_grid(draw, left, top, right, bottom, min_v, max_v)
    zero_y = _scale(0, min_v, max_v, top, bottom)
    draw.line((left, zero_y, right, zero_y), fill="#777777", width=3)
    step = (right - left) / len(values)
    bar_w = max(8, step * 0.72)
    axis_font = _font(15)
    for i, (value, label) in enumerate(zip(values, labels)):
        x0 = left + i * step + (step - bar_w) / 2
        x1 = x0 + bar_w
        y = _scale(value, min_v, max_v, top, bottom)
        fill = "#17365D" if value >= 0 else "#9A9A9A"
        draw.rectangle((x0, min(y, zero_y), x1, max(y, zero_y)), fill=fill)
        if label % 5 == 0 or label in (0, 1, 30):
            draw.text((x0 - 2, bottom + 18), str(label), fill="#555555", font=axis_font)
    return _save_chart(image)
