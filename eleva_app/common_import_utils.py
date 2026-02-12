import datetime

def clean_str(value):
    """
    Convert any Excel cell value to a clean string.

    - None -> ""
    - Numbers -> their string representation
    - Datetime/date -> ISO-ish string "YYYY-MM-DD" if appropriate, else default str(value)
    - Str -> stripped
    """
    if value is None:
        return ""

    if isinstance(value, (datetime.date, datetime.datetime)):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value).strip()

    return str(value).strip()


def parse_int_field(value, label):
    value = clean_str(value)
    if value is None or value == "":
        return None, None
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, f"{label} must be a whole number."


def stringify_cell(value):
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()
