import csv
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Dict, List, Optional

from flask import current_app, session
from flask_login import current_user
from sqlalchemy import func

from eleva_app.models import Customer, Lift, ServiceRoute


def _get_timeout_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
        if parsed > 0:
            return parsed
    except ValueError:
        pass
    return default


@dataclass
class UploadOutcome:
    header_map: Dict[str, int]
    created_count: int
    updated_count: int
    processed_rows: int
    created_items: List[Dict[str, Any]] = field(default_factory=list)
    updated_items: List[Dict[str, Any]] = field(default_factory=list)
    row_errors: List[str] = field(default_factory=list)


UPLOAD_STAGE_TIMEOUT_SECONDS = _get_timeout_env(
    "UPLOAD_STAGE_TIMEOUT_SECONDS", default=60
)
UPLOAD_TOTAL_TIMEOUT_SECONDS = _get_timeout_env(
    "UPLOAD_TOTAL_TIMEOUT_SECONDS", default=180
)


class UploadStageTimeoutError(RuntimeError):
    """Raised when a stage of the upload workflow exceeds the allowed time."""

    def __init__(self, stage: str, *, timeout: int = UPLOAD_STAGE_TIMEOUT_SECONDS):
        super().__init__(f"Timed out after {timeout} seconds while {stage}.")
        self.stage = stage
        self.timeout = timeout


def _execute_with_timeout(func, *, stage: str, timeout: int = UPLOAD_STAGE_TIMEOUT_SECONDS):
    """Execute ``func`` enforcing a timeout, raising ``UploadStageTimeoutError`` on delay."""

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    timed_out = False
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError as exc:
        timed_out = True
        future.cancel()
        raise UploadStageTimeoutError(stage, timeout=timeout) from exc
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)


def _stage_start() -> float:
    return time.monotonic()


def _check_stage_timeout(start_time: float, stage: str, *, timeout: int = UPLOAD_STAGE_TIMEOUT_SECONDS):
    if time.monotonic() - start_time > timeout:
        raise UploadStageTimeoutError(stage, timeout=timeout)


def _extract_tabular_upload(upload, *, sheet_name=None):
    from app import _ensure_openpyxl, _validate_upload_stream, load_workbook

    _validate_upload_stream(
        upload,
        allowed_extensions={".xlsx", ".csv"},
        allow_office_processing=True,
    )
    filename = (upload.filename or "").lower()
    if filename.endswith(".xlsx"):
        _ensure_openpyxl()
        upload.stream.seek(0)
        workbook = _execute_with_timeout(
            lambda: load_workbook(upload, data_only=True),
            stage="reading the uploaded Excel workbook",
        )
        try:
            worksheet = (
                workbook[sheet_name]
                if sheet_name and sheet_name in workbook.sheetnames
                else workbook.active
            )
            header = _execute_with_timeout(
                lambda: next(
                    worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
                    [],
                ),
                stage="reading header row from the uploaded workbook",
            )
            data_rows = _execute_with_timeout(
                lambda: list(worksheet.iter_rows(min_row=2, values_only=True)),
                stage="reading data rows from the uploaded workbook",
            )
        finally:
            workbook.close()

        return header, data_rows

    if filename.endswith(".csv"):
        upload.stream.seek(0)
        raw_bytes = _execute_with_timeout(
            upload.read,
            stage="reading the uploaded CSV file",
        )
        upload.stream.seek(0)
        def _decode_csv_bytes():
            try:
                return raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                return raw_bytes.decode("latin-1")

        text = _execute_with_timeout(
            _decode_csv_bytes,
            stage="decoding the uploaded CSV file",
        )
        rows = _execute_with_timeout(
            lambda: list(csv.reader(StringIO(text))),
            stage="parsing the uploaded CSV file",
        )
        header = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        return header, data_rows

    raise ValueError("Unsupported file type")


PENDING_UPLOAD_SUBDIR = "pending"


def _build_pending_upload_path(token, extension):
    from app import _normalize_extension

    if not token:
        return None
    upload_root = current_app.config["UPLOAD_FOLDER"]
    pending_root = os.path.join(upload_root, PENDING_UPLOAD_SUBDIR)
    os.makedirs(pending_root, exist_ok=True)
    ext = _normalize_extension(extension)
    if ext:
        candidate = os.path.join(pending_root, f"{token}{ext}")
        if os.path.exists(candidate):
            return candidate
    try:
        for name in os.listdir(pending_root):
            if name.startswith(token):
                return os.path.join(pending_root, name)
    except FileNotFoundError:
        return None
    if ext:
        return os.path.join(pending_root, f"{token}{ext}")
    return os.path.join(pending_root, token)


def save_pending_upload_file(upload, *, allowed_extensions=None, allow_office_processing=False):
    from app import _normalize_extension, _validate_upload_stream

    _validate_upload_stream(
        upload,
        allowed_extensions=allowed_extensions,
        allow_office_processing=allow_office_processing,
    )
    upload_root = current_app.config["UPLOAD_FOLDER"]
    pending_root = os.path.join(upload_root, PENDING_UPLOAD_SUBDIR)
    os.makedirs(pending_root, exist_ok=True)
    original_name = upload.filename or "upload"
    extension = _normalize_extension(os.path.splitext(original_name)[1])
    token = uuid.uuid4().hex
    dest_path = os.path.join(pending_root, f"{token}{extension}")
    upload.stream.seek(0)
    upload.save(dest_path)
    upload.stream.seek(0)
    return token, extension


def _clear_pending_upload(pending_token, *, remove_file=False):
    pending_uploads = session.get("pending_uploads", {})
    pending = pending_uploads.pop(pending_token, None)
    session["pending_uploads"] = pending_uploads
    session.modified = True
    if remove_file:
        pending_data = pending or {}
        file_path = pending_data.get("path")
        if not file_path:
            file_path = _build_pending_upload_path(
                pending_data.get("token"), pending_data.get("extension")
            )
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
    return pending


def cleanup_old_pending_uploads(max_age_hours: int = 24) -> int:
    """
    Delete pending upload files older than `max_age_hours` and
    return the count of files deleted.
    """

    upload_root = current_app.config["UPLOAD_FOLDER"]
    pending_root = os.path.join(upload_root, PENDING_UPLOAD_SUBDIR)

    if not os.path.isdir(pending_root):
        return 0

    cutoff = time.time() - (max_age_hours * 3600)
    deleted_count = 0

    for name in os.listdir(pending_root):
        file_path = os.path.join(pending_root, name)
        try:
            modified_time = os.path.getmtime(file_path)
        except OSError:
            continue

        if modified_time < cutoff:
            try:
                os.remove(file_path)
                deleted_count += 1
            except OSError:
                continue

    current_app.logger.info("Cleaned up %s old pending upload(s)", deleted_count)
    return deleted_count


def _extract_tabular_upload_from_path(file_path, *, sheet_name=None):
    from app import _ensure_openpyxl, load_workbook

    filename = file_path.lower()
    if filename.endswith(".xlsx"):
        _ensure_openpyxl()
        workbook = _execute_with_timeout(
            lambda: load_workbook(file_path, data_only=True),
            stage="reading the staged Excel workbook",
        )
        try:
            worksheet = (
                workbook[sheet_name]
                if sheet_name and sheet_name in workbook.sheetnames
                else workbook.active
            )
            header = _execute_with_timeout(
                lambda: next(
                    worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
                    [],
                ),
                stage="reading header row from the staged workbook",
            )
            data_rows = _execute_with_timeout(
                lambda: list(worksheet.iter_rows(min_row=2, values_only=True)),
                stage="reading data rows from the staged workbook",
            )
        finally:
            workbook.close()
        return header, data_rows

    if filename.endswith(".csv"):
        def _read_csv_file():
            with open(file_path, "rb") as fh:
                return fh.read()

        raw_bytes = _execute_with_timeout(
            _read_csv_file,
            stage="reading the staged CSV file",
        )

        def _decode_bytes():
            try:
                return raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                return raw_bytes.decode("latin-1")

        text = _execute_with_timeout(
            _decode_bytes,
            stage="decoding the staged CSV file",
        )
        rows = _execute_with_timeout(
            lambda: list(csv.reader(StringIO(text))),
            stage="parsing the staged CSV file",
        )
        header = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        return header, data_rows

    raise ValueError("Unsupported file type")


def _customer_identifier(customer, *, fallback):
    if isinstance(customer, Customer) and getattr(customer, "id", None) is not None:
        return f"existing:{customer.id}"
    return fallback


def process_customer_upload_file(file_path, *, apply_changes):
    from app import (
        clean_str,
        db,
        format_file_size,
        generate_next_customer_code,
        parse_excel_date,
        parse_int_field,
        parse_time_field,
        stringify_cell,
    )

    from app import CUSTOMER_UPLOAD_TEMPLATE_SHEET_NAME

    upload_timer = _stage_start()
    header_cells, data_rows = _extract_tabular_upload_from_path(
        file_path, sheet_name=CUSTOMER_UPLOAD_TEMPLATE_SHEET_NAME
    )
    header_timer = _stage_start()
    header_cells = header_cells or []
    header_map: Dict[str, int] = {}
    for idx, header in enumerate(header_cells or []):
        label = stringify_cell(header)
        if label:
            header_map[label] = idx
    _check_stage_timeout(header_timer, "reading header labels from the upload")

    outcome = UploadOutcome(
        header_map=header_map,
        created_count=0,
        updated_count=0,
        processed_rows=0,
    )

    customer_reference_timer = _stage_start()
    customers = Customer.query.all()
    existing_by_code: Dict[str, Any] = {
        customer.customer_code.lower(): customer
        for customer in customers
        if customer.customer_code
    }
    existing_by_external: Dict[str, Any] = {
        customer.external_customer_id.lower(): customer
        for customer in customers
        if customer.external_customer_id
    }
    _check_stage_timeout(
        customer_reference_timer,
        "loading existing customer records",
    )

    service_route_timer = _stage_start()
    service_routes = ServiceRoute.query.all()
    route_lookup: Dict[str, Any] = {}
    for route in service_routes:
        options = {route.state.lower()}
        display_name = clean_str(route.display_name)
        if display_name:
            options.add(display_name.lower())
        if route.branch:
            options.add(route.branch.lower())
            options.add(f"{route.state.lower()} · {route.branch.lower()}")
            options.add(f"{route.state.lower()}-{route.branch.lower()}")
        for option in options:
            route_lookup[option] = route
    _check_stage_timeout(
        service_route_timer,
        "loading service route reference data",
    )

    processed_codes: Dict[str, str] = {}
    processed_external_ids: Dict[str, str] = {}
    generated_codes: set[str] = set()

    for row_index, row_values in enumerate(data_rows, start=2):
        _check_stage_timeout(
            upload_timer,
            "processing the customer upload",
            timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
        )
        row_stage = _stage_start()
        row_stage_label = f"processing row {row_index}"
        try:
            if not row_values:
                continue
            row_data: Dict[str, Any] = {}
            for header, position in header_map.items():
                value = row_values[position] if position < len(row_values) else None
                row_data[header] = value

            key_fields = [
                row_data.get("External Customer ID"),
                row_data.get("Customer Code"),
                row_data.get("Company Name"),
                row_data.get("Contact Person"),
                row_data.get("Phone"),
                row_data.get("Mobile"),
                row_data.get("Email"),
                row_data.get("GST Number"),
            ]
            if not any(clean_str(stringify_cell(value)) for value in key_fields):
                continue

            outcome.processed_rows += 1

            external_id_value = clean_str(stringify_cell(row_data.get("External Customer ID")))
            customer_code_value = clean_str(stringify_cell(row_data.get("Customer Code")))
            company_name_value = clean_str(stringify_cell(row_data.get("Company Name")))
            contact_person_value = clean_str(stringify_cell(row_data.get("Contact Person")))
            phone_value = clean_str(stringify_cell(row_data.get("Phone")))
            mobile_value = clean_str(stringify_cell(row_data.get("Mobile")))
            email_value = clean_str(stringify_cell(row_data.get("Email")))
            gst_value = clean_str(stringify_cell(row_data.get("GST Number")))
            office_address_line1_value = clean_str(
                stringify_cell(row_data.get("Office Address Line 1"))
            )
            office_address_line2_value = clean_str(
                stringify_cell(row_data.get("Office Address Line 2"))
            )
            office_country_value = clean_str(stringify_cell(row_data.get("Office Country")))
            office_city_value = clean_str(stringify_cell(row_data.get("Office City")))
            office_state_value = clean_str(stringify_cell(row_data.get("Office State")))
            office_pincode_value = clean_str(stringify_cell(row_data.get("Office Pincode")))
            route_value = clean_str(stringify_cell(row_data.get("Route")))
            branch_value = clean_str(stringify_cell(row_data.get("Branch")))
            contact_designation_value = clean_str(
                stringify_cell(row_data.get("Contact Designation"))
            )
            mobile2_value = clean_str(stringify_cell(row_data.get("Mobile 2")))
            account_status_value = clean_str(stringify_cell(row_data.get("Account Status")))
            address_line1_value = clean_str(stringify_cell(row_data.get("Address Line 1")))
            address_line2_value = clean_str(stringify_cell(row_data.get("Address Line 2")))
            city_value = clean_str(stringify_cell(row_data.get("City")))
            state_value = clean_str(stringify_cell(row_data.get("State")))
            pincode_value = clean_str(stringify_cell(row_data.get("Pincode")))
            country_value = clean_str(stringify_cell(row_data.get("Country")))
            service_type_value = clean_str(stringify_cell(row_data.get("Service Type")))
            service_mode_value = clean_str(stringify_cell(row_data.get("Service Mode")))
            billing_frequency_value = clean_str(stringify_cell(row_data.get("Billing Frequency")))
            contract_value_value = clean_str(stringify_cell(row_data.get("Contract Value")))
            contract_currency_value = clean_str(stringify_cell(row_data.get("Contract Currency")))
            amc_start_value = stringify_cell(row_data.get("AMC Start (YYYY-MM-DD)"))
            amc_end_value = stringify_cell(row_data.get("AMC End (YYYY-MM-DD)"))
            amc_months_value = stringify_cell(row_data.get("AMC Months"))
            first_due_value = stringify_cell(row_data.get("First Due Date"))
            second_due_value = stringify_cell(row_data.get("Second Due Date"))
            pending_amount_value = stringify_cell(row_data.get("Pending Amount"))
            notes_value = clean_str(stringify_cell(row_data.get("Notes")))

            route = None
            if route_value:
                lookup_key = route_value.lower()
                route = route_lookup.get(lookup_key)
                if not route:
                    outcome.row_errors.append(
                        f"Row {row_index}: Route '{route_value}' does not match an active service route."
                    )
                    continue

            existing_customer = None
            if customer_code_value:
                lookup_code = customer_code_value.lower()
                if lookup_code in existing_by_code:
                    existing_customer = existing_by_code[lookup_code]
                else:
                    existing_customer = (
                        Customer.query.filter(func.lower(Customer.customer_code) == lookup_code).first()
                    )
                    existing_by_code[lookup_code] = existing_customer
            if not existing_customer and external_id_value:
                lookup_external = external_id_value.lower()
                if lookup_external in existing_by_external:
                    existing_customer = existing_by_external[lookup_external]
                else:
                    existing_customer = (
                        Customer.query.filter(func.lower(Customer.external_customer_id) == lookup_external).first()
                    )
                    existing_by_external[lookup_external] = existing_customer

            updates = []
            if route:
                route_value = route.state
                updates.append(("route", route.state, "Route"))
                if route.branch:
                    updates.append(("branch", route.branch, "Branch"))
            if branch_value and not route_value:
                outcome.row_errors.append(
                    f"Row {row_index}: Branch '{branch_value}' cannot be set without selecting a route."
                )
                continue
            if not branch_value and route and route.branch:
                branch_value = route.branch
            updates.append(("contact_person", contact_person_value, "Contact Person"))
            updates.append(("contact_designation", contact_designation_value, "Contact Designation"))
            updates.append(("phone", phone_value, "Phone"))
            updates.append(("mobile", mobile_value, "Mobile"))
            updates.append(("mobile2", mobile2_value, "Mobile 2"))
            updates.append(("email", email_value, "Email"))
            updates.append(("gst_number", gst_value, "GST Number"))
            updates.append(("office_address_line1", office_address_line1_value, "Office Address Line 1"))
            updates.append(("office_address_line2", office_address_line2_value, "Office Address Line 2"))
            updates.append(("office_country", office_country_value, "Office Country"))
            updates.append(("office_city", office_city_value, "Office City"))
            updates.append(("office_state", office_state_value, "Office State"))
            updates.append(("office_pincode", office_pincode_value, "Office Pincode"))

            if existing_customer:
                customer = existing_customer
                if not customer.customer_code:
                    outcome.row_errors.append(
                        f"Row {row_index}: Customer record is missing a customer code and cannot be updated."
                    )
                    continue
                code_key = customer.customer_code.lower()
                identifier = _customer_identifier(customer, fallback=f"existing:{id(customer)}")
                owner = processed_codes.get(code_key)
                if owner and owner != identifier:
                    outcome.row_errors.append(
                        f"Row {row_index}: Customer code '{customer.customer_code}' is duplicated in the upload."
                    )
                    continue
                processed_codes[code_key] = identifier
                outcome.updated_count += 1

                changes = []
                for attr, value, label in updates:
                    if value is None:
                        continue
                    current = getattr(customer, attr)
                    if (current or None) != value:
                        changes.append({
                            "field": label,
                            "from": current,
                            "to": value,
                        })
                        if apply_changes:
                            setattr(customer, attr, value)

                if apply_changes:
                    if country_value is None and not customer.country:
                        customer.country = "India"
                    if customer.office_country is None:
                        customer.office_country = "India"

                if changes and len(outcome.updated_items) < 20:
                    outcome.updated_items.append(
                        {
                            "customer_code": customer.customer_code,
                            "company_name": customer.company_name,
                            "changes": changes,
                        }
                    )

            else:
                if not company_name_value:
                    outcome.row_errors.append(
                        f"Row {row_index}: Company name is required for new customers."
                    )
                    continue

                if customer_code_value:
                    normalized_code = customer_code_value.lower()
                    if normalized_code in existing_by_code:
                        outcome.row_errors.append(
                            f"Row {row_index}: Customer code '{customer_code_value}' already exists."
                        )
                        continue
                    if normalized_code in processed_codes:
                        outcome.row_errors.append(
                            f"Row {row_index}: Customer code '{customer_code_value}' is duplicated in the upload."
                        )
                        continue
                    customer_code = customer_code_value
                else:
                    customer_code = generate_next_customer_code()
                    while (
                        customer_code.lower() in existing_by_code
                        or customer_code.lower() in processed_codes
                        or customer_code.lower() in generated_codes
                    ):
                        customer_code = generate_next_customer_code()
                    generated_codes.add(customer_code.lower())

                identifier = f"new:{customer_code.lower()}"
                processed_codes[customer_code.lower()] = identifier

                if apply_changes:
                    customer = Customer(
                        customer_code=customer_code,
                        company_name=company_name_value,
                    )
                    db.session.add(customer)
                    existing_by_code[customer_code.lower()] = customer
                else:
                    customer = Customer(
                        customer_code=customer_code,
                        company_name=company_name_value,
                    )
                    existing_by_code[customer_code.lower()] = customer

                outcome.created_count += 1
                if len(outcome.created_items) < 20:
                    outcome.created_items.append(
                        {
                            "customer_code": customer_code,
                            "company_name": company_name_value,
                            "route": route_value,
                            "branch": branch_value,
                        }
                    )

                if apply_changes:
                    for attr, value, _ in updates:
                        if value is not None:
                            setattr(customer, attr, value)
                    if not customer.country:
                        customer.country = "India"
                    if not customer.office_country:
                        customer.office_country = "India"

            target_identifier = None
            if existing_customer:
                customer_ref = existing_customer
            else:
                customer_ref = customer
            if isinstance(customer_ref, Customer):
                if getattr(customer_ref, "customer_code", None):
                    target_identifier = processed_codes.get(customer_ref.customer_code.lower())
                else:
                    target_identifier = identifier or f"new:{id(customer_ref)}"

            if external_id_value:
                normalized_external = external_id_value.lower()
                conflict = existing_by_external.get(normalized_external)
                conflict_identifier = None
                if isinstance(conflict, Customer):
                    conflict_identifier = _customer_identifier(conflict, fallback=f"existing:{id(conflict)}")
                elif isinstance(conflict, str):
                    conflict_identifier = conflict
                if conflict_identifier and target_identifier and conflict_identifier != target_identifier:
                    outcome.row_errors.append(
                        f"Row {row_index}: External customer ID '{external_id_value}' is already linked to another customer."
                    )
                    continue
                previous = processed_external_ids.get(normalized_external)
                if previous and target_identifier and previous != target_identifier:
                    outcome.row_errors.append(
                        f"Row {row_index}: External customer ID '{external_id_value}' is duplicated in the upload."
                    )
                    continue
                processed_external_ids[normalized_external] = target_identifier or conflict_identifier or identifier or normalized_external
                if apply_changes and isinstance(customer_ref, Customer):
                    customer_ref.external_customer_id = external_id_value
                    existing_by_external[normalized_external] = customer_ref
                elif not apply_changes:
                    existing_by_external[normalized_external] = target_identifier or identifier or normalized_external
            elif isinstance(customer_ref, Customer) and customer_ref.external_customer_id:
                processed_external_ids[customer_ref.external_customer_id.lower()] = target_identifier or identifier or f"existing:{id(customer_ref)}"

        finally:
            _check_stage_timeout(row_stage, row_stage_label)
            _check_stage_timeout(
                upload_timer,
                "processing the customer upload",
                timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
            )
    if apply_changes and (outcome.created_count or outcome.updated_count):
        _check_stage_timeout(
            upload_timer,
            "saving customer upload changes",
            timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
        )
        db.session.commit()

    return outcome


def _normalize_lookup_key(value):
    from app import clean_str, stringify_cell

    normalized = clean_str(stringify_cell(value))
    if isinstance(normalized, str) and normalized:
        return normalized.lower()
    return None


def process_lift_upload_file(file_path, *, apply_changes):
    from app import (
        calculate_amc_end_date,
        clean_str,
        db,
        normalize_amc_duration,
        normalize_amc_status,
        parse_excel_date,
        parse_time_field,
        stringify_cell,
    )

    from app import AMC_LIFT_TEMPLATE_SHEET_NAME

    row_errors: List[str] = []
    upload_timer = _stage_start()
    header_cells, data_rows = _extract_tabular_upload_from_path(
        file_path, sheet_name=AMC_LIFT_TEMPLATE_SHEET_NAME
    )
    header_timer = _stage_start()
    header_cells = header_cells or []
    header_map: Dict[str, int] = {}
    for idx, header in enumerate(header_cells or []):
        label = stringify_cell(header)
        if label:
            header_map[label] = idx
    _check_stage_timeout(header_timer, "reading header labels from the upload")

    outcome = UploadOutcome(
        header_map=header_map,
        created_count=0,
        updated_count=0,
        processed_rows=0,
    )

    customer_reference_timer = _stage_start()
    customers = Customer.query.all()
    customer_by_code = {}
    customer_by_external = {}
    customer_by_name = {}
    for customer in customers:
        code_key = _normalize_lookup_key(customer.customer_code)
        if code_key:
            customer_by_code[code_key] = customer
        external_key = _normalize_lookup_key(customer.external_customer_id)
        if external_key:
            customer_by_external[external_key] = customer
        name_key = _normalize_lookup_key(customer.company_name)
        if name_key:
            customer_by_name[name_key] = customer
    _check_stage_timeout(
        customer_reference_timer,
        "loading existing customer records",
    )

    service_route_timer = _stage_start()
    service_routes = ServiceRoute.query.all()
    route_lookup: Dict[str, Any] = {}
    for route in service_routes:
        options = {route.state.lower()}
        display_name = clean_str(route.display_name)
        if display_name:
            options.add(display_name.lower())
        if route.branch:
            options.add(route.branch.lower())
            options.add(f"{route.state.lower()} · {route.branch.lower()}")
            options.add(f"{route.state.lower()}-{route.branch.lower()}")
        for option in options:
            route_lookup[option] = route
    _check_stage_timeout(
        service_route_timer,
        "loading service route reference data",
    )

    existing_by_code: Dict[str, Optional[Lift]] = {}
    existing_by_external: Dict[str, Optional[Lift]] = {}
    processed_codes: set[str] = set()
    processed_external_ids: set[str] = set()
    generated_codes: set[str] = set()

    lift_brand_present = "Lift Brand" in header_map

    for row_index, row_values in enumerate(data_rows, start=2):
        _check_stage_timeout(
            upload_timer,
            "processing the AMC lift upload",
            timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
        )
        row_stage = _stage_start()
        row_stage_label = f"processing row {row_index}"
        try:
            if not row_values:
                continue
            row_data: Dict[str, Any] = {}
            for header, position in header_map.items():
                value = row_values[position] if position < len(row_values) else None
                row_data[header] = value

            key_fields = [
                row_data.get("Customer External ID"),
                row_data.get("Customer Code"),
                row_data.get("Customer Name"),
                row_data.get("External Lift ID"),
                row_data.get("Lift Code"),
                row_data.get("AMC Status"),
            ]
            if not any(clean_str(value) for value in key_fields):
                continue

            outcome.processed_rows += 1

            customer_external_id_value = clean_str(row_data.get("Customer External ID"))
            customer_code_value = clean_str(row_data.get("Customer Code"))
            customer_name_value = clean_str(row_data.get("Customer Name"))
            customer_external_id_key = (
                customer_external_id_value.lower() if customer_external_id_value else None
            )
            customer_code_key = customer_code_value.lower() if customer_code_value else None
            customer_name_key = customer_name_value.lower() if customer_name_value else None

            customer = None
            if customer_external_id_key and customer_external_id_key in customer_by_external:
                customer = customer_by_external[customer_external_id_key]
            if customer_code_key and customer_code_key in customer_by_code:
                customer = customer_by_code[customer_code_key]
            if (
                customer_external_id_key
                and customer_code_key
                and customer_external_id_key in customer_by_external
                and customer_code_key in customer_by_code
                and customer_by_external[customer_external_id_key].id
                != customer_by_code[customer_code_key].id
            ):
                raise ValueError(
                    f"Customer code '{customer_code_value}' does not match external ID '{customer_external_id_value}'."
                )
            if not customer and customer_name_key and customer_name_key in customer_by_name:
                customer = customer_by_name[customer_name_key]
            if not customer:
                missing_reference = (
                    customer_external_id_value
                    or customer_code_value
                    or customer_name_value
                    or "—"
                )
                raise ValueError(
                    f"Customer '{missing_reference}' was not found. Upload customers first or use customer external ID."
                )

            route_value_raw = clean_str(row_data.get("Route"))
            route_value = None
            if route_value_raw:
                lookup_key = route_value_raw.lower()
                route = route_lookup.get(lookup_key)
                if not route:
                    raise ValueError(
                        f"Route '{route_value_raw}' does not match an active service route."
                    )
                route_value = route.state

            existing_lift = None
            provided_code = clean_str(row_data.get("Lift Code"))
            provided_external = clean_str(row_data.get("External Lift ID"))

            if provided_code:
                lookup_code = provided_code.lower()
                if lookup_code in existing_by_code:
                    existing_lift = existing_by_code[lookup_code]
                else:
                    existing_lift = (
                        Lift.query.filter(func.lower(Lift.lift_code) == lookup_code).first()
                    )
                    existing_by_code[lookup_code] = existing_lift
            if not existing_lift and provided_external:
                lookup_external = provided_external.lower()
                if lookup_external in existing_by_external:
                    existing_lift = existing_by_external[lookup_external]
                else:
                    existing_lift = (
                        Lift.query.filter(func.lower(Lift.external_lift_id) == lookup_external).first()
                    )
                    existing_by_external[lookup_external] = existing_lift

            if existing_lift and existing_lift.lift_code:
                existing_by_code[existing_lift.lift_code.lower()] = existing_lift
                if existing_lift.external_lift_id:
                    existing_by_external[existing_lift.external_lift_id.lower()] = existing_lift

            if provided_external:
                normalized_external = provided_external.lower()
                if normalized_external in processed_external_ids:
                    raise ValueError(
                        f"External lift ID '{provided_external}' is duplicated in the upload."
                    )
                processed_external_ids.add(normalized_external)

            code_key = None
            if existing_lift and existing_lift.lift_code:
                code_key = existing_lift.lift_code.lower()
            elif provided_code:
                code_key = provided_code.lower()
            if code_key and code_key in processed_codes:
                display_code = provided_code or (existing_lift.lift_code if existing_lift else None)
                raise ValueError(f"Lift code '{display_code}' is duplicated in the upload.")

            amc_status_value, status_error = normalize_amc_status(
                clean_str(row_data.get("AMC Status"))
            )
            if status_error:
                raise ValueError(status_error)
            if not amc_status_value:
                raise ValueError("AMC status is required.")

            duration_key, duration_error = normalize_amc_duration(
                clean_str(row_data.get("AMC Duration"))
            )
            if duration_error:
                raise ValueError(duration_error)
            if not duration_key:
                raise ValueError("AMC duration is required.")

            amc_start = parse_excel_date(row_data.get("AMC Start (YYYY-MM-DD)"))
            if not amc_start:
                raise ValueError("AMC start date is required.")

            amc_end = parse_excel_date(row_data.get("AMC End (YYYY-MM-DD)"))
            if not amc_end:
                amc_end = calculate_amc_end_date(amc_start, duration_key)

            preferred_days_source = row_data.get("Preferred Service Days")
            preferred_days_display = (
                clean_str(preferred_days_source) if preferred_days_source is not None else None
            )
            preferred_days = preferred_days_display

            preferred_date_source = row_data.get("Preferred Service Date")
            preferred_date = None
            if preferred_date_source not in (None, ""):
                preferred_date = parse_excel_date(preferred_date_source)
                if not preferred_date:
                    raise ValueError("Preferred service date must be in a valid date format.")

            preferred_time_source = row_data.get("Preferred Service Time")
            preferred_time = None
            if preferred_time_source not in (None, ""):
                preferred_time, error = parse_time_field(
                    preferred_time_source,
                    "Preferred service time",
                )
                if error:
                    raise ValueError(error)

            next_service_due_source = row_data.get("Next Service Due")
            next_service_due = None
            if next_service_due_source not in (None, ""):
                next_service_due = parse_excel_date(next_service_due_source)
                if next_service_due is None:
                    raise ValueError("Next service due must be in a valid date format.")

            try:
                capacity_persons = int(row_data.get("Capacity (persons)") or 0) or None
            except (TypeError, ValueError):
                capacity_persons = None

            try:
                capacity_kg = int(row_data.get("Capacity (kg)") or 0) or None
            except (TypeError, ValueError):
                capacity_kg = None

            try:
                speed_mps = float(row_data.get("Speed (m/s)") or 0) or None
            except (TypeError, ValueError):
                speed_mps = None

            lift_type_value = clean_str(row_data.get("Lift Type"))
            lift_brand_value = clean_str(row_data.get("Lift Brand"))
            site_address_line1 = clean_str(row_data.get("Site Address Line 1"))
            site_address_line2 = clean_str(row_data.get("Site Address Line 2"))
            building_villa_number = clean_str(row_data.get("Building / Villa No."))
            city_value = clean_str(row_data.get("City"))
            state_value = clean_str(row_data.get("State"))
            pincode_value = clean_str(row_data.get("Pincode"))
            notes_value = clean_str(row_data.get("Notes"))

            if existing_lift:
                lift = existing_lift
                owner = existing_lift.lift_code.lower() if existing_lift.lift_code else f"existing:{id(existing_lift)}"
                if owner and owner in processed_codes:
                    raise ValueError(
                        f"Lift code '{existing_lift.lift_code}' is duplicated in the upload."
                    )
                if existing_lift.lift_code:
                    processed_codes[existing_lift.lift_code.lower()] = owner
                outcome.updated_count += 1
            else:
                generated_code = f"LIFT-{uuid.uuid4().hex[:6].upper()}"
                while (
                    generated_code.lower() in existing_by_code
                    or generated_code.lower() in processed_codes
                    or generated_code.lower() in generated_codes
                ):
                    generated_code = f"LIFT-{uuid.uuid4().hex[:6].upper()}"
                generated_codes.add(generated_code.lower())

                lift_code = provided_code or generated_code
                identifier = lift_code.lower()
                processed_codes[identifier] = identifier

                if apply_changes:
                    lift = Lift(
                        lift_code=lift_code,
                        customer_code=customer.customer_code,
                        customer=customer,
                        external_lift_id=provided_external,
                    )
                    db.session.add(lift)
                else:
                    lift = Lift(
                        lift_code=lift_code,
                        customer_code=customer.customer_code,
                        customer=customer,
                        external_lift_id=provided_external,
                    )

                outcome.created_count += 1
                if len(outcome.created_items) < 20:
                    outcome.created_items.append(
                        {
                            "lift_code": lift.lift_code,
                            "customer_code": customer.customer_code,
                            "customer_name": customer.company_name,
                            "amc_status": amc_status_value,
                        }
                    )

            if apply_changes:
                if provided_external:
                    lift.external_lift_id = provided_external
                lift.customer_code = customer.customer_code
                lift.customer = customer
                if building_villa_number is not None:
                    lift.building_villa_number = building_villa_number
                if site_address_line1 is not None:
                    lift.site_address_line1 = site_address_line1
                if site_address_line2 is not None:
                    lift.site_address_line2 = site_address_line2
                if city_value is not None:
                    lift.city = city_value
                elif not existing_lift and not lift.city and customer.city:
                    lift.city = customer.city
                if state_value is not None:
                    lift.state = state_value
                elif not existing_lift and not lift.state and customer.state:
                    lift.state = customer.state
                if pincode_value is not None:
                    lift.pincode = pincode_value
                elif not existing_lift and not lift.pincode and customer.pincode:
                    lift.pincode = customer.pincode
                if route_value:
                    lift.route = route_value
                elif not existing_lift and not lift.route and customer.route:
                    lift.route = customer.route
                if lift_type_value:
                    lift.lift_type = lift_type_value
                if lift_brand_present:
                    lift.lift_brand = lift_brand_value
                if capacity_persons is not None:
                    lift.capacity_persons = capacity_persons
                if capacity_kg is not None:
                    lift.capacity_kg = capacity_kg
                if speed_mps is not None:
                    lift.speed_mps = speed_mps
                lift.amc_status = amc_status_value
                lift.amc_start = amc_start
                lift.amc_duration_key = duration_key
                lift.amc_end = amc_end
                if preferred_days_display is not None:
                    lift.preferred_service_days = preferred_days
                elif not existing_lift:
                    lift.preferred_service_days = preferred_days
                if preferred_date_source not in (None, ""):
                    lift.preferred_service_date = preferred_date
                if preferred_time_source not in (None, ""):
                    lift.preferred_service_time = preferred_time
                if next_service_due is not None:
                    lift.next_service_due = next_service_due
                if notes_value is not None:
                    lift.notes = notes_value
                lift.last_updated_by = current_user.id
                lift.set_capacity_display()

            existing_by_code[lift.lift_code.lower()] = lift
            if provided_external:
                existing_by_external[provided_external.lower()] = lift
            elif lift.external_lift_id:
                existing_by_external[lift.external_lift_id.lower()] = lift

        except UploadStageTimeoutError:
            raise
        except ValueError as exc:
            row_errors.append(f"Row {row_index}: {exc}")
            continue
        except Exception as exc:
            current_app.logger.exception(
                "Unexpected error while processing AMC lift upload row",
                extra={"row_index": row_index},
            )
            row_errors.append(f"Row {row_index}: {exc}")
            continue
        finally:
            _check_stage_timeout(row_stage, row_stage_label)
            _check_stage_timeout(
                upload_timer,
                "processing the AMC lift upload",
                timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
            )
    if row_errors:
        if isinstance(outcome.row_errors, list):
            outcome.row_errors.extend(row_errors)
        else:
            outcome.row_errors = list(row_errors)

    if apply_changes and (outcome.created_count or outcome.updated_count):
        _check_stage_timeout(
            upload_timer,
            "saving AMC lift upload changes",
            timeout=UPLOAD_TOTAL_TIMEOUT_SECONDS,
        )
        db.session.commit()

    return outcome
