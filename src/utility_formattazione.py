def euro(x):
    try:
        return f"\u20ac {x:,.0f}".replace(",", ".")
    except Exception:
        return "\u20ac 0"


def euro2(x):
    try:
        return f"\u20ac {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "\u20ac 0,00"


def kwh(x):
    try:
        return f"{x:,.0f} kWh".replace(",", ".")
    except Exception:
        return "0 kWh"


def parse_float_it(value):
    try:
        text = str(value).strip().replace(" ", "")
        if "," in text and "." in text:
            return float(text.replace(".", "").replace(",", "."))
        if "," in text:
            return float(text.replace(".", "").replace(",", "."))
        if "." in text:
            parts = text.split(".")
            if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
                return float(text.replace(".", ""))
            return float(text)
        return float(text)
    except Exception:
        return None
