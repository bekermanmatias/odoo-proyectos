"""Restricted Odoo business API used exclusively by the GPT action.

The public controller deliberately exposes resource aliases, never arbitrary Odoo
models or methods.  This module can therefore evolve without turning Odoo's ORM
into an internet-facing RPC endpoint.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.modules.registry import Registry


class GptApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


RESOURCE_SPECS = {
    "projects": {
        "module": "project", "model": "project.project",
        "fields": ["id", "name", "partner_id", "user_id", "date_start", "date", "description", "active"],
        "write": ["name", "partner_id", "user_id", "date_start", "date", "description", "active"],
    },
    "tasks": {
        "module": "project", "model": "project.task",
        "fields": ["id", "name", "project_id", "partner_id", "user_ids", "stage_id", "tag_ids", "date_deadline", "planned_date_begin", "description", "priority", "active"],
        "write": ["name", "project_id", "partner_id", "user_ids", "stage_id", "tag_ids", "date_deadline", "planned_date_begin", "description", "priority", "active"],
    },
    "task-stages": {
        "module": "project", "model": "project.task.type",
        "fields": ["id", "name", "sequence", "fold"], "write": ["name", "sequence", "fold"],
    },
    "task-tags": {
        "module": "project", "model": "project.tags",
        "fields": ["id", "name", "color"], "write": ["name", "color"],
    },
    "contacts": {
        "module": "base", "model": "res.partner",
        "fields": ["id", "name", "email", "phone", "mobile", "company_type", "street", "city", "zip", "country_id", "vat", "active"],
        "write": ["name", "email", "phone", "mobile", "company_type", "street", "city", "zip", "country_id", "vat", "active"],
    },
    "leads": {
        "module": "crm", "model": "crm.lead",
        "fields": ["id", "name", "partner_id", "contact_name", "email_from", "phone", "expected_revenue", "probability", "stage_id", "user_id", "description", "type", "active"],
        "write": ["name", "partner_id", "contact_name", "email_from", "phone", "expected_revenue", "probability", "stage_id", "user_id", "description", "type", "active"],
    },
    "lead-stages": {
        "module": "crm", "model": "crm.stage",
        "fields": ["id", "name", "sequence", "fold"], "write": ["name", "sequence", "fold"],
    },
    "quotations": {
        "module": "sale_management", "model": "sale.order",
        "fields": ["id", "name", "partner_id", "date_order", "validity_date", "client_order_ref", "note", "state", "amount_untaxed", "amount_tax", "amount_total", "order_line"],
        "write": ["partner_id", "date_order", "validity_date", "client_order_ref", "note", "order_line"],
        "lines": "order_line",
    },
    "invoices": {
        "module": "account", "model": "account.move",
        "fields": ["id", "name", "partner_id", "move_type", "invoice_date", "invoice_date_due", "ref", "narration", "state", "amount_untaxed", "amount_tax", "amount_total", "invoice_line_ids"],
        "write": ["partner_id", "move_type", "invoice_date", "invoice_date_due", "ref", "narration", "invoice_line_ids"],
        "lines": "invoice_line_ids",
    },
    "products": {
        "module": "product", "model": "product.product",
        "fields": ["id", "name", "default_code", "barcode", "list_price", "standard_price", "qty_available", "virtual_available", "uom_id", "active"],
        "write": ["name", "default_code", "barcode", "list_price", "standard_price", "uom_id", "active"],
    },
    "stock-transfers": {
        "module": "stock", "model": "stock.picking",
        "fields": ["id", "name", "picking_type_id", "location_id", "location_dest_id", "scheduled_date", "partner_id", "state", "move_ids_without_package"],
        "write": ["picking_type_id", "location_id", "location_dest_id", "scheduled_date", "partner_id", "move_ids_without_package"],
        "lines": "move_ids_without_package",
    },
    "calendar-events": {
        "module": "calendar", "model": "calendar.event",
        "fields": ["id", "name", "start", "stop", "allday", "description", "partner_ids", "user_id", "location", "active"],
        "write": ["name", "start", "stop", "allday", "description", "partner_ids", "user_id", "location", "active"],
    },
    "activities": {
        "module": "mail", "model": "mail.activity",
        "fields": ["id", "res_name", "summary", "note", "activity_type_id", "date_deadline", "user_id"],
        "write": [],
    },
}

SENSITIVE_ACTIONS = {
    ("quotations", "confirm"): "action_confirm",
    ("invoices", "post"): "action_post",
    ("stock-transfers", "validate"): "button_validate",
}


class GptApiService:
    @staticmethod
    def database_name():
        name = os.getenv("ODOO_DB_NAME") or tools.config.get("db_name")
        if isinstance(name, (tuple, list)):
            name = name[0] if name else None
        if name and "," in name:
            name = name.split(",", 1)[0]
        if not name:
            raise GptApiError(503, "configuration_error", "ODDO_DB_NAME is not configured.")
        return name

    @staticmethod
    def integration_user_id():
        raw = os.getenv("GPT_ODOO_USER_ID", "")
        try:
            user_id = int(raw)
        except ValueError as exc:
            raise GptApiError(503, "configuration_error", "GPT_ODOO_USER_ID is not configured.") from exc
        if user_id <= 0:
            raise GptApiError(503, "configuration_error", "GPT_ODOO_USER_ID is not configured.")
        return user_id

    @classmethod
    def environment(cls):
        db_name = cls.database_name()
        user_id = cls.integration_user_id()
        registry = Registry(db_name)
        cr = registry.cursor()
        root_env = api.Environment(cr, SUPERUSER_ID, {})
        user = root_env["res.users"].browse(user_id).exists()
        if not user or not user.active:
            cr.close()
            raise GptApiError(503, "configuration_error", "The GPT integration user is unavailable.")
        env = api.Environment(cr, user_id, {})
        return env

    @staticmethod
    def close(env):
        env.cr.close()

    @staticmethod
    def installed_modules(env):
        rows = env["ir.module.module"].sudo().search_read(
            [("state", "=", "installed")], ["name"]
        )
        return {row["name"] for row in rows}

    @classmethod
    def capabilities(cls, env):
        installed = cls.installed_modules(env)
        resources = []
        for name, spec in RESOURCE_SPECS.items():
            available = spec["module"] in installed and spec["model"] in env
            resources.append({
                "resource": name,
                "available": available,
                "module": spec["module"],
                "operations": ["list", "read", "create", "update", "request_delete"] if available else [],
                "fields": [field for field in spec["fields"] if available and field in env[spec["model"]]._fields],
            })
        return {"resources": resources, "sensitive_actions": [
            {"resource": resource, "action": action}
            for resource, action in SENSITIVE_ACTIONS
            if RESOURCE_SPECS[resource]["module"] in installed
        ]}

    @classmethod
    def spec(cls, env, resource):
        spec = RESOURCE_SPECS.get(resource)
        if not spec:
            raise GptApiError(404, "unknown_resource", "This resource is not exposed by the GPT API.")
        if spec["module"] not in cls.installed_modules(env) or spec["model"] not in env:
            raise GptApiError(409, "module_not_installed", f"The Odoo module for '{resource}' is not installed.")
        return spec

    @staticmethod
    def _safe_summary(value):
        if not isinstance(value, dict):
            return ""
        redacted = {key: ("[redacted]" if any(word in key.lower() for word in ("password", "secret", "token", "key")) else val)
                    for key, val in value.items()}
        return json.dumps(redacted, default=str, ensure_ascii=False)[:4000]

    @classmethod
    def audit(cls, env, *, correlation_id, endpoint, operation, status, resource=None, record_ids=None, request_data=None, response_data=None):
        return env["gpt.api.audit"].sudo().create({
            "correlation_id": correlation_id,
            "endpoint": endpoint,
            "operation": operation,
            "resource": resource,
            "record_ids": ",".join(map(str, record_ids or [])),
            "status": status,
            "request_summary": cls._safe_summary(request_data or {}),
            "response_summary": cls._safe_summary(response_data or {}),
            "technical_user_id": env.uid,
        })

    @classmethod
    def _record(cls, env, resource, record_id):
        spec = cls.spec(env, resource)
        record = env[spec["model"]].browse(int(record_id)).exists()
        if not record:
            raise GptApiError(404, "not_found", "The requested Odoo record does not exist or is not accessible.")
        return spec, record

    @staticmethod
    def _normalize_values(model, values, writable, lines_field=None):
        if not isinstance(values, dict) or not values:
            raise GptApiError(400, "invalid_payload", "A non-empty 'values' object is required.")
        invalid = sorted(set(values) - set(writable))
        if invalid:
            raise GptApiError(400, "field_not_allowed", "One or more fields are not allowed.", {"fields": invalid})
        result = {}
        for key, value in values.items():
            field = model._fields.get(key)
            if not field:
                raise GptApiError(400, "field_not_available", f"Field '{key}' is not available in this Odoo version.")
            if key == lines_field:
                if not isinstance(value, list):
                    raise GptApiError(400, "invalid_lines", f"'{key}' must be a list.")
                result[key] = [(0, 0, line) for line in value if isinstance(line, dict)]
                if len(result[key]) != len(value):
                    raise GptApiError(400, "invalid_lines", f"Every '{key}' item must be an object.")
            elif field.type in ("many2many", "one2many"):
                if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
                    raise GptApiError(400, "invalid_relation", f"'{key}' must be a list of record IDs.")
                result[key] = [(6, 0, value)]
            else:
                result[key] = value
        return result

    @classmethod
    def list_records(cls, env, resource, filters=None, limit=25, offset=0):
        spec = cls.spec(env, resource)
        model = env[spec["model"]]
        filters = filters or {}
        if not isinstance(filters, dict):
            raise GptApiError(400, "invalid_filters", "'filters' must be an object.")
        allowed = set(spec["fields"])
        invalid = sorted(set(filters) - allowed)
        if invalid:
            raise GptApiError(400, "filter_not_allowed", "A filter is not allowed.", {"fields": invalid})
        domain = []
        for name, value in filters.items():
            if value is None:
                continue
            field = model._fields.get(name)
            if not field:
                continue
            operator = "=" if field.type not in ("char", "text", "html") or name == "id" else "ilike"
            domain.append((name, operator, value))
        readable = [name for name in spec["fields"] if name in model._fields]
        limit = max(1, min(int(limit or 25), 100))
        offset = max(0, int(offset or 0))
        return {"records": model.search_read(domain, readable, limit=limit, offset=offset, order="id desc"), "limit": limit, "offset": offset}

    @classmethod
    def get_record(cls, env, resource, record_id):
        spec, record = cls._record(env, resource, record_id)
        readable = [name for name in spec["fields"] if name in record._fields]
        return {"record": record.read(readable)[0]}

    @classmethod
    def create_record(cls, env, resource, values):
        spec = cls.spec(env, resource)
        model = env[spec["model"]]
        normalized = cls._normalize_values(model, values, spec["write"], spec.get("lines"))
        if resource == "invoices":
            normalized.setdefault("move_type", "out_invoice")
        record = model.create(normalized)
        return {"record": cls.get_record(env, resource, record.id)["record"]}

    @classmethod
    def update_record(cls, env, resource, record_id, values):
        spec, record = cls._record(env, resource, record_id)
        normalized = cls._normalize_values(record, values, spec["write"], spec.get("lines"))
        record.write(normalized)
        return {"record": cls.get_record(env, resource, record.id)["record"]}

    @classmethod
    def create_activity(cls, env, values):
        cls.spec(env, "activities")
        allowed = {"model", "record_id", "activity_type_id", "summary", "note", "date_deadline", "user_id"}
        invalid = sorted(set(values or {}) - allowed)
        if invalid or not values.get("model") or not values.get("record_id") or not values.get("activity_type_id"):
            raise GptApiError(400, "invalid_activity", "model, record_id and activity_type_id are required.", {"fields": invalid})
        target = env[values["model"]].browse(int(values["record_id"])).exists()
        if not target:
            raise GptApiError(404, "not_found", "The activity target is not accessible.")
        activity_values = {
            "res_model_id": env["ir.model"]._get(values["model"]).id,
            "res_id": target.id,
            "activity_type_id": int(values["activity_type_id"]),
            "summary": values.get("summary"), "note": values.get("note"),
            "date_deadline": values.get("date_deadline"), "user_id": values.get("user_id") or env.uid,
        }
        activity = env["mail.activity"].create(activity_values)
        return {"record": activity.read(["id", "summary", "date_deadline", "user_id", "res_name"])[0]}

    @classmethod
    def request_confirmation(cls, env, *, correlation_id, endpoint, resource, record_id, operation, payload=None):
        spec, record = cls._record(env, resource, record_id)
        action_label = "delete" if operation == "delete" else operation
        summary = f"Confirm {action_label} on {resource} #{record.id} ({record.display_name})."
        audit = cls.audit(
            env, correlation_id=correlation_id, endpoint=endpoint, operation=operation,
            status="pending", resource=resource, record_ids=[record.id], request_data=payload or {},
            response_data={"summary": summary},
        )
        confirmation = env["gpt.api.confirmation"].sudo().create({
            "token": secrets.token_urlsafe(24), "operation": operation, "resource": resource,
            "record_id": record.id, "payload_json": json.dumps(payload or {}), "summary": summary,
            "expires_at": fields.Datetime.now() + timedelta(minutes=10),
            "technical_user_id": env.uid, "audit_id": audit.id,
        })
        return {"status": "pending_confirmation", "confirmation_id": confirmation.token, "summary": summary, "expires_at": confirmation.expires_at}

    @classmethod
    def execute_confirmation(cls, env, token):
        confirmation = env["gpt.api.confirmation"].sudo().search([("token", "=", token)], limit=1)
        if not confirmation:
            raise GptApiError(404, "confirmation_not_found", "The confirmation does not exist.")
        if confirmation.state != "pending":
            raise GptApiError(409, "confirmation_not_pending", "This confirmation is no longer pending.")
        if confirmation.expires_at < fields.Datetime.now():
            confirmation.write({"state": "expired"})
            raise GptApiError(410, "confirmation_expired", "The confirmation expired; request the operation again.")
        if confirmation.technical_user_id.id != env.uid:
            raise GptApiError(403, "confirmation_owner_mismatch", "This confirmation belongs to another integration user.")
        spec, record = cls._record(env, confirmation.resource, confirmation.record_id)
        if confirmation.operation == "delete":
            record.unlink()
            result = {"deleted": True, "record_id": confirmation.record_id}
        else:
            method = SENSITIVE_ACTIONS.get((confirmation.resource, confirmation.operation))
            if not method:
                raise GptApiError(400, "invalid_confirmation", "This operation cannot be confirmed.")
            getattr(record, method)()
            result = {"executed": True, "record_id": record.id, "action": confirmation.operation}
        confirmation.write({"state": "executed"})
        confirmation.audit_id.write({"status": "success", "response_summary": cls._safe_summary(result)})
        return result

    @classmethod
    def list_confirmations(cls, env):
        now = fields.Datetime.now()
        env["gpt.api.confirmation"].sudo().search([
            ("state", "=", "pending"), ("expires_at", "<", now)
        ]).write({"state": "expired"})
        rows = env["gpt.api.confirmation"].sudo().search_read(
            [("state", "=", "pending"), ("technical_user_id", "=", env.uid)],
            ["token", "operation", "resource", "record_id", "summary", "expires_at"], limit=50,
        )
        return {"confirmations": [
            {"confirmation_id": row.pop("token"), **row} for row in rows
        ]}

    @classmethod
    def list_audit(cls, env, limit=25):
        limit = max(1, min(int(limit or 25), 100))
        rows = env["gpt.api.audit"].sudo().search_read(
            [("technical_user_id", "=", env.uid)],
            ["create_date", "correlation_id", "endpoint", "operation", "resource", "record_ids", "status"],
            limit=limit, order="id desc",
        )
        return {"audit": rows}

    @classmethod
    def assert_authorized(cls, authorization_header):
        expected = os.getenv("GPT_ODOO_API_KEY", "")
        if not expected:
            raise GptApiError(503, "configuration_error", "GPT_ODOO_API_KEY is not configured.")
        supplied = (authorization_header or "").removeprefix("Bearer ").strip()
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise GptApiError(401, "unauthorized", "A valid Bearer API key is required.")

    @staticmethod
    def translate_exception(error):
        if isinstance(error, GptApiError):
            raise error
        if isinstance(error, AccessError):
            raise GptApiError(403, "odoo_access_denied", "The integration user is not allowed to perform this operation.") from error
        if isinstance(error, (UserError, ValidationError, ValueError)):
            raise GptApiError(400, "odoo_validation_error", str(error)) from error
        raise error
