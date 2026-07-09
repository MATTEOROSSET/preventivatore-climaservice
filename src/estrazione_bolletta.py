import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from pypdf import PdfReader
import pytesseract

from .utility_formattazione import parse_float_it


MONTH_NAMES = {
    "gen": 1,
    "gennaio": 1,
    "feb": 2,
    "febbraio": 2,
    "mar": 3,
    "marzo": 3,
    "apr": 4,
    "aprile": 4,
    "mag": 5,
    "maggio": 5,
    "giu": 6,
    "giugno": 6,
    "lug": 7,
    "luglio": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "sett": 9,
    "settembre": 9,
    "ott": 10,
    "ottobre": 10,
    "nov": 11,
    "novembre": 11,
    "dic": 12,
    "dicembre": 12,
}


def extract_text_from_uploaded(uploaded_file, on_error=None):
    if uploaded_file is None:
        return ""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    content_type = (getattr(uploaded_file, "type", "") or "").lower()
    try:
        data = uploaded_file.getvalue()
    except Exception:
        data = uploaded_file.read()

    if name.endswith(".pdf") or content_type == "application/pdf":
        return extract_text_from_pdf_bytes(data, on_error=on_error)

    if content_type.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
        return extract_text_from_image_bytes(data, on_error=on_error)

    if on_error:
        on_error("Formato file non supportato. Carica una bolletta in PDF, JPG o PNG.")
    return ""


def extract_text_from_pdf(uploaded_file, on_error=None):
    if uploaded_file is None:
        return ""
    try:
        data = uploaded_file.getvalue()
    except Exception:
        data = uploaded_file.read()
    return extract_text_from_pdf_bytes(data, on_error=on_error)


def extract_text_from_pdf_bytes(pdf_bytes, on_error=None):
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
            text += "\n"
        if _has_enough_text(text):
            return text
        ocr_text = extract_text_from_pdf_ocr(pdf_bytes, on_error=on_error, page_count=len(reader.pages))
        return ocr_text or text
    except Exception as exc:
        if on_error:
            on_error(f"Lettura PDF non riuscita: {exc}")
        return ""


def extract_text_from_image_bytes(image_bytes, on_error=None):
    try:
        image = Image.open(BytesIO(image_bytes))
        return _ocr_image(image, on_error=on_error)
    except Exception as exc:
        if on_error:
            on_error(f"Lettura immagine non riuscita: {exc}")
        return ""


def extract_text_from_pdf_ocr(pdf_bytes, on_error=None, max_pages=6, page_count=None):
    pdftoppm = _find_pdftoppm()
    if not pdftoppm:
        if on_error:
            on_error("PDF composto da immagini: manca il convertitore PDF->immagine per eseguire l'OCR.")
        return ""
    if not _has_tesseract():
        if on_error:
            on_error("Il PDF sembra composto da immagini: per leggerlo serve il motore OCR Tesseract.")
        return ""

    tmp_dir = _new_ocr_work_dir()
    try:
        pdf_path = tmp_dir / "bolletta.pdf"
        output_prefix = tmp_dir / "pagina"
        pdf_path.write_bytes(pdf_bytes)
        last_page = max(1, min(int(page_count or max_pages), int(max_pages)))
        try:
            subprocess.run(
                [pdftoppm, "-png", "-r", "220", "-f", "1", "-l", str(last_page), str(pdf_path), str(output_prefix)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", errors="ignore").strip()
            if on_error:
                on_error(f"OCR PDF non riuscito durante la conversione delle pagine: {detail or exc}")
            return ""
        except Exception as exc:
            if on_error:
                on_error(f"OCR PDF non riuscito durante la conversione delle pagine: {exc}")
            return ""

        texts = []
        for image_path in sorted(tmp_dir.glob("pagina-*.png")):
            try:
                texts.append(_ocr_image(Image.open(image_path), on_error=on_error))
            except Exception:
                continue
        text = "\n".join(part for part in texts if part)
        if not text and on_error:
            on_error("PDF composto da immagini: OCR non riuscito o motore OCR non disponibile.")
        return text
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _find_pdftoppm():
    candidates = []
    found = shutil.which("pdftoppm.exe") or shutil.which("pdftoppm")
    if found:
        candidates.append(Path(found))
    found_cmd = shutil.which("pdftoppm.cmd")
    if found_cmd:
        cmd_path = Path(found_cmd)
        candidates.append(cmd_path)
        parts = list(cmd_path.parents)
        if len(parts) >= 2:
            candidates.append(parts[1] / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe")

    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".exe":
            return str(candidate)
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() != ".cmd":
            return str(candidate)
    return ""


def _new_ocr_work_dir():
    root = Path(__file__).resolve().parent.parent / "tmp_ocr"
    root.mkdir(parents=True, exist_ok=True)
    work_dir = root / f"ocr_{uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def _has_tesseract():
    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False
    except Exception:
        return False


def _ocr_image(image, on_error=None):
    try:
        prepared = _prepare_image_for_ocr(image)
        try:
            return pytesseract.image_to_string(prepared, lang="ita+eng", config="--psm 6")
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(prepared, lang="eng", config="--psm 6")
    except pytesseract.TesseractNotFoundError:
        if on_error:
            on_error("Il file sembra un'immagine: per leggerlo serve il motore OCR Tesseract.")
        return ""
    except Exception as exc:
        if on_error:
            on_error(f"OCR non riuscito: {exc}")
        return ""


def _prepare_image_for_ocr(image):
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    width, height = image.size
    if max(width, height) < 2200:
        scale = 2200 / max(width, height)
        image = image.resize((int(width * scale), int(height * scale)))
    return image


def _has_enough_text(text):
    clean = re.sub(r"\s+", "", text or "")
    return len(clean) >= 250


def extract_bill_data(text):
    data = {
        "cliente": "",
        "indirizzo": "",
        "localita": "",
        "pod": "",
        "consumo_mese_kwh": None,
        "consumo_mese_fonte": "",
        "consumi_annui_kwh": None,
        "consumi_annui_fonte": "",
        "totale_bolletta": None,
        "costo_energia_stimato": None,
        "costo_energia_fonte": "",
        "potenza_impegnata": None,
        "f1": None,
        "f2": None,
        "f3": None,
        "consumi_mensili_kwh": [],
        "consumi_mensili_fonte": "",
    }
    if not text:
        return data

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    for pattern in [
        r"(IT\d{3}[A-Z0-9]{8,})",
        r"POD.*?(IT\d{3}[A-Z0-9]{8,})",
        r"Codice POD\s+(IT\d{3}[A-Z0-9]{8,})",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            data["pod"] = match.group(1).strip()
            break

    for index, line in enumerate(lines):
        lowered = line.lower()

        if "intestazione contratto" in lowered and index + 1 < len(lines):
            data["cliente"] = lines[index + 1]
            data["indirizzo"] = lines[index + 2] if index + 2 < len(lines) else ""
            data["localita"] = lines[index + 3] if index + 3 < len(lines) else ""
            break

        if line.startswith("Ciao ") and "," in line:
            data["cliente"] = line.replace("Ciao", "").replace(",", "").strip()

        if "la tua fornitura di energia elettrica e in:" in lowered and index + 1 < len(lines):
            data["indirizzo"] = lines[index + 1]
            if index + 2 < len(lines):
                data["localita"] = lines[index + 2]

    if not data["cliente"]:
        for index, line in enumerate(lines):
            if (
                re.match(r"^[A-ZÀ-Ù' ]{6,}$", line)
                and index + 1 < len(lines)
                and any(token in lines[index + 1].upper() for token in ["VIA", "PIAZZA", "CORSO"])
            ):
                data["cliente"] = line.title()
                data["indirizzo"] = lines[index + 1].title()
                data["localita"] = lines[index + 2].title() if index + 2 < len(lines) else ""
                break

    for pattern in [
        r"([\d,\.]+)\s*kW\s*IT\d{3}[A-Z0-9]{8,}",
        r"Potenza contrattualmente impegnata[:\s]+([\d,\.]+)\s*kW",
        r"Potenza impegnata[:\s]+([\d,\.]+)\s*kW",
        r"Potenza impegnata kW[:\s]+([\d,\.]+)",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            data["potenza_impegnata"] = parse_float_it(match.group(1))
            break

    for pattern in [
        r"Consumo rilevato.*?F1\s+F2\s+F3\s+Totale energia\s+([\d\.]+)\s*kWh\s+([\d\.]+)\s*kWh\s+([\d\.]+)\s*kWh",
        r"Consumi di energia attiva fatturata.*?reale\s+(\d+)\s+(\d+)\s+(\d+)",
        r"reale\s+(\d+)\s+(\d+)\s+(\d+)\s+[\d,]+",
        r"Totale kWh\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE | re.DOTALL)
        if match:
            values = [parse_float_it(value) for value in match.groups()[:3]]
            if all(value is not None for value in values):
                data["f1"], data["f2"], data["f3"] = values
                data["consumo_mese_kwh"] = sum(values)
                data["consumo_mese_fonte"] = "Letto dalla bolletta come somma F1/F2/F3"
                break

    if not data["consumo_mese_kwh"]:
        for pattern in [
            r"Quanto ho consumato\?\s*([\d\.]+)\s*kWh",
            r"Consumo del periodo\s*(?:di fatturazione)?\s*([\d\.]+)\s*kWh",
            r"Consumo del periodo\s*([\d\.]+)\s*kWh",
            r"Consumo totale fatturato del periodo\s*([\d\.]+)\s*kWh",
            r"Consumo totale fatturato nel periodo di fatturazione\s*([\d,\.]+)\s*kWh",
        ]:
            match = re.search(pattern, joined, re.IGNORECASE)
            if match:
                data["consumo_mese_kwh"] = parse_float_it(match.group(1))
                data["consumo_mese_fonte"] = "Letto dalla bolletta"
                break

    for pattern in [
        r"In un anno hai consumato\s*([\d\.]+)\s*kWh",
        r"CONSUMO ANNUO\s*([\d\.]+)\s*kWh",
        r"Consumo annuo.*?([\d\.]+)\s*kWh",
        r"Consumo annuo\s*(?:aggiornato.*?)?\s*([\d\.]+)\s*kWh",
        r"Tot\. consumo\s*([\d\.]+)\s*kWh",
        r"consumo annuo aggiornato.*?([\d\.]+)\s*kWh",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE | re.DOTALL)
        if match:
            value = parse_float_it(match.group(1))
            if value and value > 0:
                data["consumi_annui_kwh"] = value
                data["consumi_annui_fonte"] = "Letto dalla bolletta"
                break

    monthly_values = extract_monthly_consumption(lines)
    if monthly_values:
        data["consumi_mensili_kwh"] = monthly_values
        data["consumi_mensili_fonte"] = "Dettaglio/storico mensile letto dalla bolletta"
        if not data["consumi_annui_kwh"]:
            data["consumi_annui_kwh"] = sum(monthly_values)
            data["consumi_annui_fonte"] = "Calcolato dalla somma dei 12 mesi letti in bolletta"

    for pattern in [
        r"Totale da pagare\s*([\d\.,]+)\s*(?:EUR|€)",
        r"Totale Bolletta\s*([\d\.,]+)\s*(?:EUR|€)",
        r"Quanto pago per questa bolletta\?\s*([\d\.,]+)\s*(?:EUR|€)",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            data["totale_bolletta"] = parse_float_it(match.group(1))
            break

    for pattern in [
        r"Quota per consumi\s+[\d,\.]+\s*kWh\s+([\d,\.]+)\s*(?:EUR|€)/kWh",
        r"Quota consumi\s+[\d,\.]+\s*kWh\s+([\d,\.]+)\s*(?:EUR|€)/kWh",
        r"Costo medio unitario(?: della bolletta)?\s*([\d,\.]+)\s*(?:EUR|€|euro)?\s*/?\s*kWh",
        r"Costo medio unitario della spesa per la materia energia\s*([\d,\.]+)\s*(?:EUR|€|euro)?\s*/?\s*kWh",
        r"Prezzo (?:energia|unitario).*?([\d,\.]+)\s*(?:EUR|€|euro)\s*/?\s*kWh",
        r"([\d,\.]+)\s*(?:EUR|€|euro)\s*/\s*kWh",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            data["costo_energia_stimato"] = parse_float_it(match.group(1))
            data["costo_energia_fonte"] = "Letto dalla bolletta"
            break

    if not data["costo_energia_stimato"] and data["consumo_mese_kwh"] and data["totale_bolletta"]:
        data["costo_energia_stimato"] = data["totale_bolletta"] / data["consumo_mese_kwh"]
        data["costo_energia_fonte"] = "Stimato da totale bolletta diviso consumo del periodo"

    return data


def extract_monthly_consumption(lines):
    historical = extract_historical_band_consumption(lines)
    if historical:
        return historical

    values_by_month = {}
    month_pattern = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
    for line in lines:
        normalized = line.lower().replace(".", " ")
        for match in re.finditer(rf"\b({month_pattern})\b[^\d]{{0,25}}([\d\.,]+)\s*kwh", normalized, re.IGNORECASE):
            month = MONTH_NAMES.get(match.group(1).lower())
            value = parse_float_it(match.group(2))
            if month and value and 0 < value < 5000:
                values_by_month[month] = value

    if len(values_by_month) == 12:
        return [values_by_month[index] for index in range(1, 13)]

    joined = "\n".join(lines)
    for pattern in [
        r"consumi\s+(?:degli\s+)?ultimi\s+12\s+mesi(.*?)(?:totale|riepilogo|letture|spesa|fornitura)",
        r"andamento\s+consumi(.*?)(?:totale|riepilogo|letture|spesa|fornitura)",
    ]:
        match = re.search(pattern, joined, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        numbers = [parse_float_it(value) for value in re.findall(r"(\d{1,4}(?:[\.,]\d{1,2})?)\s*kWh", match.group(1), re.IGNORECASE)]
        numbers = [value for value in numbers if value and 0 < value < 5000]
        if len(numbers) >= 12:
            return numbers[:12]

    return []


def extract_historical_band_consumption(lines):
    joined = "\n".join(lines)
    match = re.search(r"Storico consumi(.*?)Potenza massima prelevata", joined, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    block = match.group(1)
    if "Fascia F1" not in block or "Fascia F2" not in block or "Fascia F3" not in block:
        return []

    before_f1, rest = block.split("Fascia F1", 1)
    between_f1_f2, rest = rest.split("Fascia F2", 1)
    between_f2_f3, after_f3 = rest.split("Fascia F3", 1)

    f1_prefix = _small_ints(before_f1)
    f1_f2_numbers = _small_ints(between_f1_f2)
    f2_f3_numbers = _small_ints(between_f2_f3)
    f3_suffix = _small_ints(after_f3)

    if not f1_prefix or not f3_suffix:
        return []

    prefix_len = len(f1_prefix)
    suffix_len = len(f3_suffix)
    expected_middle_len = prefix_len + suffix_len
    if len(f1_f2_numbers) < expected_middle_len or len(f2_f3_numbers) < expected_middle_len:
        return []

    f1 = f1_prefix + f1_f2_numbers[:suffix_len]
    f2 = f1_f2_numbers[suffix_len:suffix_len + prefix_len] + f2_f3_numbers[:suffix_len]
    f3 = f2_f3_numbers[suffix_len:suffix_len + prefix_len] + f3_suffix

    if not (len(f1) == len(f2) == len(f3) and len(f1) >= 12):
        return []

    monthly = [f1[index] + f2[index] + f3[index] for index in range(len(f1) - 12, len(f1))]
    return monthly if sum(monthly) > 0 else []


def _small_ints(text):
    values = []
    for value in re.findall(r"\b\d{1,4}\b", text):
        parsed = int(value)
        if parsed < 1000:
            values.append(parsed)
    return values
