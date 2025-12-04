import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from flask import current_app

from eleva_app import db
from eleva_app.models import DrawingSite, DrawingVersion
from eleva_app.uploads import _extract_tabular_upload
from app import (
    UploadStageTimeoutError,
    clean_str,
    parse_int_field,
    stringify_cell,
)
from utils.excel_utils import iter_rows_from_xlsx


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

OPTIONAL_HEADERS = {"LIFT IDENTIFIER"}

FIELD_MAP = {
    "Project No.": "project_no",
    "CLIENT NAME": "client_name",
    "SITE LOCATION": "site_location",
    "DRG NUMBER": "drg_number",
    "DRG BY": "drg_by",
    "REV. NO.": "rev_no",
    "DRG APPROVAL": "drg_approval",
    "LIFT TYPE": "lift_type",
    "LIFT IDENTIFIER": "lift_identifier",
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
    filename = (upload.filename or "").lower()
    if filename.endswith(".xlsx"):
        upload.stream.seek(0)
        headers, row_dicts = iter_rows_from_xlsx(upload.stream)
        data_rows = [
            [row_dict.get(header) for header in headers]
            for row_dict in row_dicts
        ]
        return headers, data_rows

    return _extract_tabular_upload(upload)


def _find_or_create_site(
    project_no, client_name, site_location, lift_type, lift_identifier=None
):
    existing_site = (
        DrawingSite.query.filter(
            DrawingSite.project_no == project_no,
            DrawingSite.client_name == client_name,
            DrawingSite.site_location == site_location,
            DrawingSite.lift_type == lift_type,
            DrawingSite.lift_identifier == lift_identifier,
        )
        .order_by(DrawingSite.id.asc())
        .first()
    )

    if existing_site:
        return existing_site, False

    site = DrawingSite(
        project_no=project_no,
        client_name=client_name,
        site_location=site_location,
        lift_type=lift_type,
        lift_identifier=lift_identifier,
    )
    db.session.add(site)
    db.session.flush()
    return site, True


def _apply_latest_version(site: DrawingSite):
    site.apply_latest_version()


def process_drawing_history_upload(upload) -> DrawingHistoryUploadResult:
    result = DrawingHistoryUploadResult()
    touched_sites = []

    try:
        header_cells, data_rows = _extract_drawing_history_upload(upload)
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

    # Add any optional headers that are present to the header map
    for header in OPTIONAL_HEADERS:
        if header in header_map:
            continue
        for candidate in header_map.keys():
            if candidate.strip().lower() == header.lower():
                header_map[header] = header_map[candidate]
                break

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

        site, site_created = _find_or_create_site(
            project_no,
            mapped_values.get("client_name"),
            mapped_values.get("site_location"),
            mapped_values.get("lift_type"),
            mapped_values.get("lift_identifier"),
        )

        # Keep the site record aligned with the latest metadata from the sheet.
        site.project_no = project_no or site.project_no
        site.client_name = mapped_values.get("client_name") or site.client_name
        site.site_location = mapped_values.get("site_location") or site.site_location
        site.lift_type = mapped_values.get("lift_type") or site.lift_type
        site.lift_identifier = mapped_values.get("lift_identifier") or site.lift_identifier

        version = (
            DrawingVersion.query.filter(
                DrawingVersion.drawing_site_id == site.id,
                DrawingVersion.drawing_number == drg_number,
                DrawingVersion.revision_no == rev_no,
            ).first()
        )

        is_new_version = version is None
        if not version:
            version = DrawingVersion(
                drawing_site_id=site.id,
                drawing_number=drg_number,
                revision_no=rev_no,
            )
            db.session.add(version)
            try:
                site.versions.append(version)
            except Exception:
                pass

        version.approval_status = mapped_values.get("drg_approval")
        version.revision_reason = mapped_values.get("remarks")
        if not version.created_at:
            version.created_at = datetime.datetime.utcnow()

        if is_new_version:
            result.created_count += 1
        elif not site_created:
            result.updated_count += 1

        _apply_latest_version(site)
        site.last_updated = datetime.datetime.utcnow()
        touched_sites.append(site)

    for site in {s for s in touched_sites if s}:
        _apply_latest_version(site)
        if site.versions and not site.last_updated:
            latest = sorted(
                site.versions,
                key=lambda v: (v.created_at or datetime.datetime.min, v.id or 0),
                reverse=True,
            )
            site.last_updated = (
                latest[0].created_at if latest and latest[0].created_at else datetime.datetime.utcnow()
            )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save drawing history upload changes")
        result.fatal_error = "Could not save drawing history records due to a database error."

    return result
