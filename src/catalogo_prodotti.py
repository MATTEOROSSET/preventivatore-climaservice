import re
from pathlib import Path

from pypdf import PdfReader


def carica_catalogo(app_dir):
    app_dir = Path(app_dir).resolve()
    project_dir = app_dir.parent
    listini = list(project_dir.glob("Listino*.pdf")) + list((app_dir / "listini").glob("*.pdf"))
    schede_dir = project_dir / "schede tecniche"
    schede = list(schede_dir.glob("*.pdf")) + list((app_dir / "schede_tecniche").glob("*.pdf"))

    moduli = []
    batterie = []
    fonti = []
    for listino in listini:
        text = _pdf_text(listino)
        moduli.extend(_parse_moduli(text, listino))
        batterie.extend(_parse_batterie(text, listino))
        fonti.append(str(listino))

    schede_info = _leggi_schede_tecniche(schede)
    for item in moduli:
        info = _match_scheda(item["tipo_pannelli"], schede_info)
        item["scheda_tecnica"] = info.get("fonte", "")
        item["descrizione_tecnica"] = info.get("descrizione") or _descrizione_modulo_base(item)
    for item in batterie:
        info = _match_scheda(item["marca_modello"], schede_info)
        item["scheda_tecnica"] = info.get("fonte", "")
        item["descrizione_tecnica"] = info.get("descrizione") or _descrizione_batteria_base(item)
    schede_usate = {item.get("scheda_tecnica") for item in moduli + batterie if item.get("scheda_tecnica")}
    moduli_da_schede, batterie_da_schede = _prodotti_da_schede(schede_info, schede_usate)

    return {
        "pannelli": sorted(_pannelli_da_moduli_e_schede(moduli, moduli_da_schede), key=lambda x: x["tipo_pannelli"]),
        "moduli": sorted(_dedupe(moduli, ("tipo_pannelli", "numero_pannelli", "potenza_kwp", "prezzo_iva")), key=lambda x: (x["tipo_pannelli"], x["numero_pannelli"])),
        "batterie": sorted(_dedupe(batterie, ("marca_modello", "capacita_kwh", "prezzo_nuovo")), key=lambda x: (x["marca_modello"], x["capacita_kwh"])),
        "moduli_da_schede": sorted(_dedupe(moduli_da_schede, ("tipo_pannelli", "potenza_pannello_wp", "scheda_tecnica")), key=lambda x: x["tipo_pannelli"]),
        "batterie_da_schede": sorted(_dedupe(batterie_da_schede, ("marca_modello", "capacita_kwh", "scheda_tecnica")), key=lambda x: x["marca_modello"]),
        "fonti": fonti,
        "schede": schede_info,
    }


def prezzo_suggerito(modulo, batteria=None):
    prezzo = float((modulo or {}).get("prezzo_iva") or 0)
    if batteria:
        prezzo += float(batteria.get("prezzo_nuovo") or batteria.get("prezzo") or 0)
    return prezzo


def prodotto_piu_vicino(items, target, key):
    if not items:
        return None
    return min(items, key=lambda item: abs(float(item.get(key) or 0) - float(target or 0)))


def configurazione_da_pannello(moduli, pannello, numero_pannelli):
    if not pannello:
        return {}
    candidates = [
        item for item in moduli
        if _same_panel(item, pannello) and int(item.get("numero_pannelli") or 0) == int(numero_pannelli or 0)
    ]
    if candidates:
        return candidates[0]
    return {}


def _pannelli_da_moduli_e_schede(moduli, moduli_da_schede):
    items = []
    for item in moduli:
        items.append({
            "tipo_pannelli": item.get("tipo_pannelli", ""),
            "modello_pannelli": item.get("modello_pannelli", ""),
            "potenza_pannello_wp": item.get("potenza_pannello_wp") or 0,
            "inverter": item.get("inverter", "SAJ"),
            "scheda_tecnica": item.get("scheda_tecnica", ""),
            "descrizione_tecnica": item.get("descrizione_tecnica", ""),
            "solo_scheda": False,
        })
    for item in moduli_da_schede:
        items.append(item)
    return _dedupe(items, ("tipo_pannelli", "modello_pannelli", "potenza_pannello_wp", "scheda_tecnica"))


def _same_panel(config, pannello):
    return (
        _norm(config.get("tipo_pannelli")) == _norm(pannello.get("tipo_pannelli"))
        and round(float(config.get("potenza_pannello_wp") or 0), 2) == round(float(pannello.get("potenza_pannello_wp") or 0), 2)
    )


def _dedupe(items, keys):
    seen = set()
    results = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        results.append(item)
    return results


def _pdf_text(path):
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _parse_moduli(text, fonte):
    results = []
    headings = [
        (_clean_spaces(match.group(1)).upper(), _parse_float_it(match.group(2)))
        for match in re.finditer(r"MODULI\s+(.+?)\s+DA\s+(\d+(?:,\d+)?)\s+Wp", text, flags=re.I)
    ]
    blocks = list(re.finditer(
        r"POTENZA IMPIANTO\s+.+?PREZZO IVA COMPRESA\s+.+?(?=\nPREZZO AL KWP|\nPACCHETTO|\nLISTINO|\Z)",
        text,
        flags=re.I | re.S,
    ))
    for idx, block_match in enumerate(blocks[:len(headings)]):
        block = block_match.group(0)
        tipo, wp = headings[idx]
        potenze = _numbers_after(block, "POTENZA IMPIANTO")
        numeri = [int(round(v)) for v in _numbers_after(block, "NUMERO MODULI")]
        produzioni = _numbers_after(block, "PRODUZIONE STIMATA")
        prezzi = _prices_after(block, "PREZZO IVA COMPRESA")
        inverter_line = _line_after(block, "INVERTER")
        inverter_values = _clean_spaces(inverter_line).split()

        count = min(len(potenze), len(numeri), len(prezzi))
        for pos in range(count):
            inverter = inverter_values[pos] if pos < len(inverter_values) else (inverter_values[0] if inverter_values else "SAJ")
            results.append({
                "tipo_pannelli": tipo,
                "modello_pannelli": _modello_pannelli(tipo, wp),
                "potenza_pannello_wp": wp,
                "numero_pannelli": numeri[pos],
                "potenza_kwp": potenze[pos],
                "inverter": inverter,
                "produzione_stimata": produzioni[pos] if pos < len(produzioni) else None,
                "prezzo_iva": prezzi[pos],
                "fonte_listino": str(fonte),
            })
    return results


def _parse_batterie(text, fonte):
    section_match = re.search(r"LISTINO ACCUMULATORI(.*?)(?:LISTINO COLONNINE|Optional|$)", text, flags=re.I | re.S)
    if not section_match:
        return []
    section = section_match.group(1)
    results = []
    for line in section.splitlines():
        line = _clean_spaces(line)
        match = re.match(r"(.+?)\s+(\d+(?:,\d+)?)\s*kWh\s+€\s*([\d\.,]+)\s+€\s*([\d\.,]+)", line, flags=re.I)
        if not match:
            continue
        name = _clean_spaces(match.group(1)).upper()
        results.append({
            "marca_modello": name,
            "capacita_kwh": _parse_float_it(match.group(2)),
            "prezzo_esistente": _parse_float_it(match.group(3)),
            "prezzo_nuovo": _parse_float_it(match.group(4)),
            "prezzo": _parse_float_it(match.group(4)),
            "fonte_listino": str(fonte),
        })
    return results


def _leggi_schede_tecniche(paths):
    info = []
    seen = set()
    for path in paths:
        marker = _norm(path.stem)
        if marker in seen:
            continue
        seen.add(marker)
        text = _pdf_text(path)
        info.append({
            "fonte": str(path),
            "nome": path.stem,
            "descrizione": _riassunto_tecnico(text, path.stem),
            "testo": text[:15000],
        })
    return info


def _prodotti_da_schede(schede, schede_usate):
    moduli = []
    batterie = []
    for scheda in schede:
        if scheda.get("fonte") in schede_usate:
            continue
        text = scheda.get("testo", "")
        name = scheda.get("nome", "")
        full_text = f"{name}\n{text}"
        kind = _tipo_scheda(full_text)
        if kind == "modulo":
            wp = _potenza_wp_da_scheda(full_text) or 0
            if wp <= 0:
                continue
            tipo = _nome_prodotto_da_scheda(name)
            moduli.append({
                "tipo_pannelli": tipo,
                "modello_pannelli": tipo,
                "potenza_pannello_wp": wp,
                "numero_pannelli": 1,
                "potenza_kwp": wp / 1000,
                "inverter": "SAJ",
                "produzione_stimata": None,
                "prezzo_iva": 0,
                "fonte_listino": "",
                "scheda_tecnica": scheda.get("fonte", ""),
                "descrizione_tecnica": scheda.get("descrizione", ""),
                "solo_scheda": True,
            })
        elif kind == "batteria":
            capacita = _capacita_kwh_da_scheda(full_text) or 0
            tipo = _nome_prodotto_da_scheda(name)
            batterie.append({
                "marca_modello": tipo,
                "capacita_kwh": capacita,
                "prezzo_esistente": 0,
                "prezzo_nuovo": 0,
                "prezzo": 0,
                "fonte_listino": "",
                "scheda_tecnica": scheda.get("fonte", ""),
                "descrizione_tecnica": scheda.get("descrizione", ""),
                "solo_scheda": True,
            })
    return moduli, batterie


def _tipo_scheda(text):
    norm = _norm(text)
    if any(word in norm for word in ["batteria", "battery", "storage", "accumulo", "luna2000"]):
        return "batteria"
    if _potenza_wp_da_scheda(text):
        return "modulo"
    if any(word in norm for word in ["modulo", "module", "vitovolt", "trina", "wp", "watt"]):
        return "modulo"
    return ""


def _potenza_wp_da_scheda(text):
    title = text.splitlines()[0] if text.splitlines() else text
    title_candidates = []
    for match in re.finditer(r"(\d{3,4})(?:\s*[-/]\s*(\d{3,4}))?\s*(?:Wp|Watt|W)?\b", title, flags=re.I):
        for group in match.groups():
            if group:
                value = float(group)
                if 250 <= value <= 800:
                    title_candidates.append(value)
        value = float(match.group(1))
        if 250 <= value <= 800:
            title_candidates.append(value)
    if title_candidates:
        return max(title_candidates)

    candidates = []
    for match in re.finditer(r"(\d{3,4})\s*(?:Wp|Watt|W)\b", text, flags=re.I):
        value = float(match.group(1))
        if 250 <= value <= 800:
            candidates.append(value)
    return max(candidates) if candidates else None


def _capacita_kwh_da_scheda(text):
    candidates = []
    for match in re.finditer(r"(\d+(?:[,.]\d+)?)\s*kWh", text, flags=re.I):
        value = _parse_float_it(match.group(1))
        if 2 <= value <= 40:
            candidates.append(value)
    return candidates[0] if candidates else None


def _nome_prodotto_da_scheda(name):
    text = re.sub(r"[_-]+", " ", str(name))
    text = re.sub(r"\s+", " ", text).strip()
    return text.upper()


def _match_scheda(nome, schede):
    nome_norm = _norm(nome)
    best = {}
    best_score = 0
    for scheda in schede:
        haystack = _norm(scheda["nome"] + " " + scheda.get("testo", "")[:2000])
        score = sum(1 for token in nome_norm.split() if len(token) > 2 and token in haystack)
        if score > best_score:
            best = scheda
            best_score = score
    return best if best_score > 0 else {}


def _riassunto_tecnico(text, fallback_name):
    lines = [_clean_spaces(line) for line in text.splitlines()]
    lines = [line for line in lines if 20 <= len(line) <= 180]
    keywords = [
        "garanzia", "efficienza", "n-type", "topcon", "vetro", "potenza", "energia utilizzabile",
        "profondita", "scarica", "temperatura", "comunicazione", "installazione", "modulare",
        "monitoraggio", "protezione", "silenzioso", "dimensioni",
    ]
    selected = []
    seen = set()
    for line in lines:
        norm = _norm(line)
        if norm in seen:
            continue
        if any(keyword in norm for keyword in keywords):
            selected.append(line)
            seen.add(norm)
        if len(selected) >= 4:
            break
    if selected:
        return " ".join(selected)
    return f"Prodotto {fallback_name}: caratteristiche tecniche come da scheda caricata."


def _descrizione_modulo_base(item):
    return (
        f"Moduli fotovoltaici {item['tipo_pannelli']} modello {item['modello_pannelli']}, "
        f"potenza unitaria {item['potenza_pannello_wp']:.0f} Wp."
    )


def _descrizione_batteria_base(item):
    return f"Sistema di accumulo {item['marca_modello']} da {item['capacita_kwh']:.1f} kWh."


def _section_end(text, start):
    candidates = [pos for pos in [text.find("LISTINO ACCUMULATORI", start), text.find("LISTINO COLONNINE", start)] if pos >= 0]
    return min(candidates) if candidates else len(text)


def _line_after(block, label):
    match = re.search(rf"{re.escape(label)}\s+(.+)", block, flags=re.I)
    return match.group(1).strip() if match else ""


def _numbers_after(block, label):
    line = _line_after(block, label)
    return [_parse_float_it(value) for value in re.findall(r"\d+(?:[,.]\d+)?", line)]


def _prices_after(block, label):
    line = _line_after(block, label)
    return [_parse_float_it(value) for value in re.findall(r"([\d.]+,\d{2})\s*€", line)]


def _parse_float_it(value):
    text = str(value).strip().replace("€", "").replace(" ", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        return float(text.replace(".", "").replace(",", "."))
    if "," in text:
        return float(text.replace(".", "").replace(",", "."))
    if "." in text:
        parts = text.split(".")
        if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
            return float(text.replace(".", ""))
    return float(text)


def _modello_pannelli(tipo, wp):
    if "TRINA" in tipo:
        return "TSM-NEG9R.28"
    if "VIESSMANN" in tipo or "VIESMANN" in tipo:
        return "Vitovolt 300-DG"
    return f"{tipo} {wp:.0f} Wp"


def _clean_spaces(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value):
    return _clean_spaces(value).lower().replace("à", "a").replace("è", "e").replace("ì", "i").replace("ò", "o").replace("ù", "u")
