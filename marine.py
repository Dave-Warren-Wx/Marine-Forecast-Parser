import requests
import pandas as pd
from datetime import datetime, timedelta
import re
import os

# === CONFIG ===
ZONES = {
    "AMZ651": "miami",  # Miami coastal waters (3-letter day abbrev)
    "GMZ044": "keys"    # Keys coastal waters (full day names)
}
OUTPUT_DIR = "../data/output"
OUTPUT_FILE = "marine_forecast.csv"
CWF_URLS = {
    "AMZ651": "https://forecast.weather.gov/product.php?site=MFL&issuedby=MFL&product=CWF",
    "GMZ044": "https://forecast.weather.gov/product.php?site=NWS&issuedby=KEY&product=CWF"
}

# === FUNCTION TO FETCH AND EXTRACT FORECAST ===
def get_zone_forecast(zone_id, zone_type):
    try:
        url = CWF_URLS[zone_id]
        response = requests.get(url)
        response.raise_for_status()
        # Remove HTML tags
        text = re.sub(r"<.*?>", "", response.text, flags=re.DOTALL)
    except Exception as e:
        print(f"⚠ Error fetching {zone_id}: {e}")
        return None

    # --- Extract the full zone block ---
    if zone_id == "GMZ044":
        pattern_zone = re.compile(
            r"(?:GMZ042[\->]044|GMZ044)(?:[^\n]*)\n(.*?)(?=\n\$|\Z)",
            re.DOTALL
        )
    else:
        pattern_zone = re.compile(
            rf"{zone_id}(?:[^\n]*)\n(.*?)(?=\n\$|\Z)",
            re.DOTALL
        )

    zone_match = pattern_zone.search(text)
    if not zone_match:
        print(f"⚠ No forecast found for zone {zone_id}")
        return None

    zone_text = zone_match.group(1)
    lines = zone_text.splitlines()

    # --- Detect Small Craft Caution / Advisory ---
    text_lower = zone_text.lower()
    caution_flag = 1 if "caution" in text_lower else 0
    advisory_flag = 1 if "advisory" in text_lower else 0
    both_flag = 1 if ("caution" in text_lower and "advisory" in text_lower) else 0
    no_alert_flag = 1 if (caution_flag == 0 and advisory_flag == 0) else 0

    # --- Extract advisory/caution text (between first and last '...') ---
    advisory_text = ""
    if ("caution" in text_lower or "advisory" in text_lower):
        advisory_match = re.search(r"\.\.\.(.*?)\.\.\.", zone_text, re.DOTALL)
        if advisory_match:
            advisory_text = advisory_match.group(1).strip()

    # --- Determine which day to capture ---
    now = datetime.now()
    if now.hour < 12:
        # Before noon: use today
        target_day = "Today"
        day_labels = ["TODAY", now.strftime("%a").upper(), now.strftime("%A").upper()]
    else:
        # After noon: use tomorrow
        target_day = "Tomorrow"
        tomorrow = now + timedelta(days=1)
        day_labels = [tomorrow.strftime("%a").upper(), tomorrow.strftime("%A").upper()]

    # --- Line-by-line capture of forecast for target day ---
    forecast_lines = []
    capture = False

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Start capturing when we hit the target day header
        if any(line_clean.startswith(f".{label}") for label in day_labels):
            capture = True
            # Remove the label from the line text
            for label in day_labels:
                line_clean = re.sub(rf"^\.{label}\.*", "", line_clean, flags=re.I).strip()
            if line_clean:
                forecast_lines.append(line_clean)
            continue

        # Stop if another forecast header starts
        if capture and line_clean.startswith(".") and not any(line_clean.startswith(f".{label}") for label in day_labels):
            break

        if capture:
            forecast_lines.append(line_clean)

    if not forecast_lines:
        print(f"⚠ No forecast found for {zone_id} on target day ({day_labels})")
        return None

    # --- Combine forecast lines ---
    full_text = " ".join([re.sub(r"\s+", " ", l) for l in forecast_lines])

    # --- Trim forecast at the next day header (e.g., TONIGHT, THU, FRIDAY, etc.) ---
    # This prevents leftover text like "RSDAY..."
    cutoff_pattern = re.compile(
        r"\b(?:TONIGHT|NIGHT|MON|TUE|WED|THU|FRI|SAT|SUN|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\b",
        re.IGNORECASE
    )
    cutoff_match = cutoff_pattern.search(full_text)
    if cutoff_match:
        forecast_text = full_text[:cutoff_match.start()].strip()
    else:
        forecast_text = full_text.strip()

    return {
        "Zone": zone_id,
        "City": ZONES[zone_id].capitalize(),
        "Day": target_day,  # Returns "Today" or "Tomorrow"
        "Forecast": forecast_text,
        "SmallCraftCaution": caution_flag,
        "SmallCraftAdvisory": advisory_flag,
        "BothMentioned": both_flag,
        "NoAlert": no_alert_flag,
        "AdvisoryText": advisory_text,
        "Retrieved": datetime.now().strftime("%Y-%m-%d %I:%M %p")
    }



# === GATHER FORECASTS ===
forecast_list = []
for zone_id, zone_type in ZONES.items():
    result = get_zone_forecast(zone_id, zone_type)
    if result:
        forecast_list.append(result)

# --- SAVE RESULTS ---
df = pd.DataFrame(forecast_list)

# --- Direction mapping ---
DIRECTION_MAP = {
    "north": "N",
    "northeast": "NE",
    "east": "E",
    "southeast": "SE",
    "south": "S",
    "southwest": "SW",
    "west": "W",
    "northwest": "NW"
}

# --- Normalize full direction to abbreviation ---
def normalize_wind(text):
    if not isinstance(text, str) or not text:
        return ""
    text = text.lower()
    
    for full, abbr in DIRECTION_MAP.items():
        text = re.sub(rf"\b{full}\b", abbr, text)
    
    text = re.sub(r"\bwinds?\b", "", text)
    text = re.sub(r"\s+to\s+", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b(knots?|kt)\b", "kts", text)
    return text

# --- Flexible wind extraction with optional gusts, all units as kts ---
def extract_wind_field(forecast_text):
    if not isinstance(forecast_text, str):
        return ""
    
    match = re.search(
        r"\b((?:north|northeast|east|southeast|south|southwest|west|northwest|N|NE|E|SE|S|SW|W|NW)"
        r"(?:\s*to\s*(?:north|northeast|east|southeast|south|southwest|west|northwest|N|NE|E|SE|S|SW|W|NW))?"
        r"\s*winds?\s*(?:around\s*|near\s*)?\d{1,2}(?:\s*(?:to|-)\s*\d{1,2})?)\s*(?:kt|kts|knots)",
        forecast_text, re.I
    )
    
    if not match:
        return ""
    
    wind_speed = normalize_wind(match.group(1))
    wind_speed = re.sub(r"\b(around|near)\b\s*", "", wind_speed, flags=re.I)

    gust_match = re.search(
        r"gusts?\s*(?:up to\s*)?(\d{1,2})\s*(?:kt|kts|knots)?",
        forecast_text, re.I
    )
    if gust_match:
        gust_value = gust_match.group(1)
        wind_speed += f" ({gust_value})"

    return f"{wind_speed} kts"

# --- Extract seas field ---
def extract_seas_field(forecast_text):
    if not isinstance(forecast_text, str):
        return ""

    seas_match = re.search(
        r"Seas\s+(?:around\s+)?([\d.]+(?:\s*(?:to|-)\s*[\d.]+)?)\s*(?:feet|ft)"
        r"(?:,\s*occasionally\s*(?:to\s*)?([\d.]+)\s*(?:feet|ft))?",
        forecast_text, re.I
    )

    if seas_match:
        base_range = seas_match.group(1).strip()
        occasional = seas_match.group(2)
        base_range = re.sub(r"\s*to\s*", "-", base_range)

        if re.search(r"\bSeas\s+around\s+", forecast_text, re.I):
            base_range = "around " + base_range

        seas_text = base_range
        if occasional:
            seas_text += f" ({occasional})"
        seas_text += " ft"
        return seas_text.strip()
    return ""

def extract_intracoastal(forecast_text):
    if not isinstance(forecast_text, str):
        return ""

    match = re.search(
        r"(Intracoastal|Nearshore)\s+waters\s+(?:will be\s+|are\s+)?([^.]+)",
        forecast_text,
        re.I
    )
    if not match:
        return ""

    desc = match.group(2).strip().lower()
    desc = re.split(r",|becoming", desc)[0].strip()
    desc = desc.replace("in exposed areas", "").strip()

    # --- Normalize severity terms ---
    if "rough" in desc:
        return "rough"
    elif "choppy" in desc:
        return "choppy"
    elif "moderate" in desc:
        return "mod chop"
    elif "light" in desc:
        return "light chop"
    elif "smooth" in desc:
        return "smooth"

    return desc

# --- Apply extraction ---
df["Winds"] = df["Forecast"].apply(extract_wind_field)
df["Seas"] = df["Forecast"].apply(extract_seas_field)
df["Intracoastal"] = df["Forecast"].apply(extract_intracoastal)

# --- Clean up spacing ---
for col in ["Seas", "Intracoastal"]:
    df[col] = df[col].str.replace(r"\s+", " ", regex=True).str.strip()

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Local save
local_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
df.to_csv(local_path, index=False)

# Network save
network_path = r"\\WFOR-TVSDC-2\DigitalMedia\Custom\ImportedData\marine_forecast.csv"
df.to_csv(network_path, index=False)
