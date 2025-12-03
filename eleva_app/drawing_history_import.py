import importlib
from dataclasses import dataclass, field
from typing import List, Optional

from flask import current_app

from eleva_app import db
from eleva_app.models import DrawingHistory
from eleva_app.uploads import _extract_tabular_upload
from app import (
    MissingDependencyError,
    OPENPYXL_MISSING_MESSAGE,
    PANDAS_MISSING_MESSAGE,
    UploadStageTimeoutError,
    clean_str,
    parse_int_field,
    stringify_cell,
)


REQUIRED_HEADERS = {
    "Project No.",
    "CLIENT NAME",
    "SITE LOCATION",
    "DRG NUMBER",
    "DRG BY",
    "REV. NO.",
    "DRG APPROVAL",
    "LIFT TYPE",
    "SHAFT INNER DIMS (Actual)",
    "CAR INNER DIMS",
    "NO. OF PASS. (Actual)",
    "NO. OF PASS. (Quoted)",
    "FLR. LEVEL",
    "LANDING DOOR OPENING",
    "NO. OF SIDES OF STRUCT.",
}

FIELD_MAP = {
    "Project No.": "project_no",
    "CLIENT NAME": "client_name",
    "SITE LOCATION": "site_location",
    "DRG NUMBER": "drg_number",
    "DRG BY": "drg_by",
    "REV. NO.": "rev_no",
    "DRG APPROVAL": "drg_approval",
    "LIFT TYPE": "lift_type",
    "SHAFT INNER DIMS (Actual)": "shaft_inner_dims",
    "CAR INNER DIMS": "car_inner_dims",
    "NO. OF PASS. (Actual)": "num_pass_actual",
    "NO. OF PASS. (Quoted)": "num_pass_quoted",
    "FLR. LEVEL": "floor_level",
    "LANDING DOOR OPENING": "landing_door_opening",
    "NO. OF SIDES OF STRUCT.": "num_sides_struct",
}

INTEGER_HEADERS = {
    "NO. OF PASS. (Actual)",
    "NO. OF PASS. (Quoted)",
    "NO. OF SIDES OF STRUCT.",
}


def _get_pandas():
    if importlib.util.find_spec("pandas") is None:
        raise MissingDependencyError(PANDAS_MISSING_MESSAGE)
    return importlib.import_module("pandas")


@dataclass
class DrawingHistoryUploadResult:
    processed_rows: int = 0
    created_count: int = 0
    updated_count: int = 0
    row_errors: List[str] = field(default_factory=list)
    fatal_error: Optional[str] = None


def _collect_row_data(row_values, header_map):
    row_data = {}
    has_value = False
    for header, position in header_map.items():
        value = row_values[position] if position < len(row_values) else None
        cell_value = stringify_cell(value)
        if cell_value:
            has_value = True
        row_data[header] = value
    return row_data, has_value


def _parse_int(value, label):
    parsed, error = parse_int_field(value, label)
    if error:
        return None, f"Invalid integer in {label}"
    return parsed, None


def _extract_drawing_history_upload(upload):
    pd = _get_pandas()
    filename = (upload.filename or "").lower()
    if filename.endswith(".xlsx"):
        from app import _ensure_openpyxl

        _ensure_openpyxl()
        upload.stream.seek(0)
        df_raw = pd.read_excel(upload, header=None)
        if df_raw.empty:
            return [], []

        header_row = df_raw.iloc[0].fillna("")
        df = df_raw.iloc[1:].copy()
        df.columns = header_row
        df = df.loc[:, df.columns.astype(str).str.strip() != ""]
        df.columns = [str(column).strip() for column in df.columns]
        return list(df.columns), df.values.tolist()

    return _extract_tabular_upload(upload)


def process_drawing_history_upload(upload) -> DrawingHistoryUploadResult:
    result = DrawingHistoryUploadResult()

    try:
        header_cells, data_rows = _extract_drawing_history_upload(upload)
    except MissingDependencyError:
        result.fatal_error = OPENPYXL_MISSING_MESSAGE
        return result
    except ValueError:
        result.fatal_error = "Upload a valid .xlsx or .csv Drawing History file."
        return result
    except UploadStageTimeoutError as exc:
        result.fatal_error = str(exc)
        return result
    except Exception:
        current_app.logger.exception("Failed to read drawing history upload")
        result.fatal_error = (
            "There was a problem reading this file. Please check that you're using "
            "the correct Drawing History template and try again."
        )
        return result

    header_map = {}
    for idx, header in enumerate(header_cells or []):
        label = stringify_cell(header)
        if label:
            header_map[label] = idx

    missing_headers = [label for label in REQUIRED_HEADERS if label not in header_map]
    if missing_headers:
        result.fatal_error = (
            "The uploaded sheet is missing required columns: "
            + ", ".join(sorted(missing_headers))
        )
        return result

    for row_index, row_values in enumerate(data_rows or [], start=2):
        if not row_values:
            continue
        row_data, has_value = _collect_row_data(row_values, header_map)
        if not has_value:
            continue

        result.processed_rows += 1
        issues: List[str] = []

        mapped_values = {}
        for header, field_name in FIELD_MAP.items():
            raw_value = row_data.get(header)
            mapped_values[field_name] = clean_str(stringify_cell(raw_value)) or None

        project_no = mapped_values.get("project_no")
        drg_number = mapped_values.get("drg_number")
        rev_no = mapped_values.get("rev_no")

        if not project_no and not drg_number:
            issues.append("Missing Project No. and DRG NUMBER")

        for integer_header in INTEGER_HEADERS:
            parsed, error = _parse_int(row_data.get(integer_header), integer_header)
            if error:
                issues.append(error)
            mapped_values[FIELD_MAP[integer_header]] = parsed

        remarks = clean_str(stringify_cell(row_data.get("Remarks")))
        mapped_values["remarks"] = remarks or None

        if issues:
            result.row_errors.append(f"Row {row_index}: {'; '.join(issues)}")
            continue

        existing = (
            DrawingHistory.query.filter(
                DrawingHistory.project_no == project_no,
                DrawingHistory.drg_number == drg_number,
                DrawingHistory.rev_no == rev_no,
            ).first()
        )

        is_new = existing is None
        record = existing or DrawingHistory()

        for field_name, value in mapped_values.items():
            setattr(record, field_name, value or None)
        record.is_active = True if record.is_active is None else record.is_active

        if is_new:
            db.session.add(record)
            result.created_count += 1
        else:
            result.updated_count += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save drawing history upload changes")
        result.fatal_error = "Could not save drawing history records due to a database error."

    return result
