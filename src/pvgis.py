import requests


def _get_without_proxy(url, *, params, headers=None, timeout=20):
    session = requests.Session()
    session.trust_env = False
    return session.get(url, params=params, headers=headers, timeout=timeout)


def suggest_system(consumi_annui, profile="Realistico"):
    consumi = consumi_annui or 0
    if consumi <= 3000:
        kwp, batteria = 4.5, 5
    elif consumi <= 5000:
        kwp, batteria = 6.0, 10
    elif consumi <= 8000:
        kwp, batteria = 8.5, 15
    else:
        kwp, batteria = 10.0, 15

    if profile in ["Auto elettrica futura", "Pompa di calore futura"]:
        kwp += 2.0
        batteria += 5
    elif profile == "Massimizzare indipendenza energetica":
        batteria += 5

    return round(kwp, 2), batteria


def geocode_nominatim(address, on_error=None):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1, "countrycodes": "it"}
        headers = {"User-Agent": "ClimaserviceFV/1.0"}
        response = _get_without_proxy(url, params=params, headers=headers, timeout=12)
        response.raise_for_status()
        results = response.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as exc:
        if on_error:
            on_error(f"Geocoding non riuscito: {exc}")
    return None, None


def call_pvgis(lat, lon, peakpower, angle, aspect, loss=14):
    try:
        url = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
        params = {
            "lat": lat,
            "lon": lon,
            "peakpower": peakpower,
            "loss": loss,
            "angle": angle,
            "aspect": aspect,
            "outputformat": "json",
            "browser": 0,
        }
        response = _get_without_proxy(url, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        annual = payload.get("outputs", {}).get("totals", {}).get("fixed", {}).get("E_y")
        monthly = payload.get("outputs", {}).get("monthly", {}).get("fixed", [])
        months = [month.get("month") for month in monthly]
        values = [month.get("E_m") for month in monthly]
        return annual, months, values, None
    except Exception as exc:
        return None, [], [], str(exc)


def pvgis_estimate_fallback(potenza_kwp, orientamento, inclinazione):
    base_specific_yield = 1030
    orient_abs = abs(float(orientamento))
    orient_factor = max(0.72, 1 - (orient_abs / 180) * 0.22)
    orient_factor = orient_factor / (1 - (90 / 180) * 0.22)
    tilt_factor = max(0.90, 1 - abs(float(inclinazione) - 30) * 0.003)
    return potenza_kwp * base_specific_yield * orient_factor * tilt_factor
