from __future__ import annotations

import json
import uuid

from odoo import http
from odoo.http import request
from werkzeug.wrappers import Response

from ..services import GptApiError, GptApiService
from ..services.api_service import SENSITIVE_ACTIONS
from ..services.openapi import openapi_document


def json_response(payload, status=200):
    return Response(json.dumps(payload, default=str, ensure_ascii=False), status=status, content_type="application/json")


class GptOdooApiController(http.Controller):
    def _run(self, endpoint, operation, callback, *, resource=None, request_data=None):
        correlation_id = request.httprequest.headers.get("X-Request-ID") or str(uuid.uuid4())
        env = None
        try:
            GptApiService.assert_authorized(request.httprequest.headers.get("Authorization"))
            env = GptApiService.environment()
            result = callback(env)
            if operation not in {"request_delete", "request_action", "confirm"}:
                GptApiService.audit(
                    env, correlation_id=correlation_id, endpoint=endpoint, operation=operation,
                    status="success", resource=resource, request_data=request_data or {}, response_data=result,
                )
            # auth='none' routes use a cursor opened by the bridge, so persist the
            # audited operation explicitly rather than relying on Odoo's session.
            env.cr.commit()
            return json_response({"correlation_id": correlation_id, **result})
        except Exception as error:  # Convert expected Odoo errors without exposing internals.
            try:
                GptApiService.translate_exception(error)
            except GptApiError as api_error:
                if env:
                    env.cr.rollback()
                    GptApiService.audit(
                        env, correlation_id=correlation_id, endpoint=endpoint, operation=operation,
                        status="error", resource=resource, request_data=request_data or {},
                        response_data={"code": api_error.code, "message": api_error.message},
                    )
                    env.cr.commit()
                return json_response({"error": {"code": api_error.code, "message": api_error.message, "details": api_error.details}, "correlation_id": correlation_id}, api_error.status)
            raise
        finally:
            if env:
                GptApiService.close(env)

    @http.route("/gpt-api/openapi.json", type="http", auth="none", methods=["GET"], csrf=False)
    def openapi(self, **kwargs):
        return json_response(openapi_document())

    @http.route("/gpt-api/v1/health", type="http", auth="none", methods=["GET"], csrf=False)
    def health(self, **kwargs):
        return self._run("/health", "health", lambda env: {"status": "ok", "database": GptApiService.database_name()})

    @http.route("/gpt-api/v1/capabilities", type="http", auth="none", methods=["GET"], csrf=False)
    def capabilities(self, **kwargs):
        return self._run("/capabilities", "capabilities", lambda env: GptApiService.capabilities(env))

    @http.route("/gpt-api/v1/records/<string:resource>", type="http", auth="none", methods=["GET", "POST"], csrf=False)
    def records(self, resource, **kwargs):
        if request.httprequest.method == "GET":
            filters = request.httprequest.args.get("filters")
            try:
                filters = json.loads(filters) if filters else {}
            except json.JSONDecodeError:
                return json_response({"error": {"code": "invalid_filters", "message": "filters must be valid JSON."}}, 400)
            return self._run(
                f"/records/{resource}", "list", lambda env: GptApiService.list_records(
                    env, resource, filters, request.httprequest.args.get("limit", 25), request.httprequest.args.get("offset", 0)
                ), resource=resource, request_data={"filters": filters},
            )
        data = request.httprequest.get_json(silent=True) or {}
        if resource == "activities":
            return self._run(f"/records/{resource}", "create", lambda env: GptApiService.create_activity(env, data.get("values", {})), resource=resource, request_data=data)
        return self._run(f"/records/{resource}", "create", lambda env: GptApiService.create_record(env, resource, data.get("values", {})), resource=resource, request_data=data)

    @http.route("/gpt-api/v1/records/<string:resource>/<int:record_id>", type="http", auth="none", methods=["GET", "PATCH", "DELETE"], csrf=False)
    def record(self, resource, record_id, **kwargs):
        method = request.httprequest.method
        if method == "GET":
            return self._run(f"/records/{resource}/{record_id}", "read", lambda env: GptApiService.get_record(env, resource, record_id), resource=resource)
        if method == "PATCH":
            data = request.httprequest.get_json(silent=True) or {}
            return self._run(f"/records/{resource}/{record_id}", "update", lambda env: GptApiService.update_record(env, resource, record_id, data.get("values", {})), resource=resource, request_data=data)
        return self._run(
            f"/records/{resource}/{record_id}", "request_delete",
            lambda env: GptApiService.request_confirmation(
                env, correlation_id=request.httprequest.headers.get("X-Request-ID") or str(uuid.uuid4()),
                endpoint=f"/records/{resource}/{record_id}", resource=resource, record_id=record_id, operation="delete"
            ), resource=resource,
        )

    @http.route("/gpt-api/v1/records/<string:resource>/<int:record_id>/actions/<string:action>", type="http", auth="none", methods=["POST"], csrf=False)
    def request_action(self, resource, record_id, action, **kwargs):
        if (resource, action) not in SENSITIVE_ACTIONS:
            return json_response({"error": {"code": "action_not_allowed", "message": "This sensitive action is not exposed."}}, 404)
        return self._run(
            f"/records/{resource}/{record_id}/actions/{action}", "request_action",
            lambda env: GptApiService.request_confirmation(
                env, correlation_id=request.httprequest.headers.get("X-Request-ID") or str(uuid.uuid4()),
                endpoint=f"/records/{resource}/{record_id}/actions/{action}", resource=resource, record_id=record_id, operation=action
            ), resource=resource,
        )

    @http.route("/gpt-api/v1/confirmations", type="http", auth="none", methods=["GET"], csrf=False)
    def confirmations(self, **kwargs):
        return self._run("/confirmations", "list_confirmations", lambda env: GptApiService.list_confirmations(env))

    @http.route("/gpt-api/v1/confirmations/<string:token>/confirm", type="http", auth="none", methods=["POST"], csrf=False)
    def confirm(self, token, **kwargs):
        return self._run("/confirmations/confirm", "confirm", lambda env: GptApiService.execute_confirmation(env, token))

    @http.route("/gpt-api/v1/audit", type="http", auth="none", methods=["GET"], csrf=False)
    def audit(self, **kwargs):
        return self._run("/audit", "audit", lambda env: GptApiService.list_audit(env, request.httprequest.args.get("limit", 25)))
