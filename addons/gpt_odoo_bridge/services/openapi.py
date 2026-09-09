"""OpenAPI document served at /gpt-api/openapi.json for the GPT Action editor."""


def openapi_document():
    resource_parameter = {
        "name": "resource", "in": "path", "required": True,
        "schema": {"type": "string", "enum": ["projects", "tasks", "task-stages", "task-tags", "contacts", "leads", "lead-stages", "quotations", "invoices", "products", "stock-transfers", "calendar-events", "activities"]},
    }
    record_id_parameter = {
        "name": "record_id", "in": "path", "required": True,
        "schema": {"type": "integer", "minimum": 1},
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Pupuia Odoo GPT API",
            "version": "1.0.0",
            "description": "Restricted, audited Odoo business operations. Never use confirmation endpoints until the user explicitly confirms the pending operation.",
        },
        "servers": [{"url": "https://api.pupuia.com/gpt-api/v1"}],
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "API key"}},
            "schemas": {
                "Values": {
                    "type": "object",
                    "description": "Allowed fields depend on the resource and are returned by getCapabilities.",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "Rich Odoo HTML. Use semantic <h2>, <h3>, <p>, <ul>, <ol>, <li>, and <strong>; do not use Markdown, inline CSS, or long unstructured text.",
                        },
                        "project_id": {"type": "integer"}, "partner_id": {"type": "integer"},
                        "project_ids": {"type": "array", "items": {"type": "integer"}, "description": "Projects linked to a task stage."},
                        "user_id": {"type": "integer"}, "stage_id": {"type": "integer"},
                        "tag_ids": {"type": "array", "items": {"type": "integer"}},
                        "priority": {"type": "string", "enum": ["0", "1", "2", "3"], "description": "Task priority: 0 normal, 1 low, 2 high, 3 urgent (three stars)."},
                        "date_deadline": {"type": "string"}, "email": {"type": "string"},
                        "phone": {"type": "string"}, "note": {"type": "string"},
                        "ref": {"type": "string"}, "invoice_date": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "Resource": {"type": "string", "enum": ["projects", "tasks", "task-stages", "task-tags", "contacts", "leads", "lead-stages", "quotations", "invoices", "products", "stock-transfers", "calendar-events", "activities"]},
                "Error": {"type": "object", "properties": {"error": {"type": "object"}, "correlation_id": {"type": "string"}}},
            },
        },
        "paths": {
            "/health": {"get": {"operationId": "getHealth", "summary": "Check API health", "responses": {"200": {"description": "Healthy"}}}},
            "/capabilities": {"get": {"operationId": "getCapabilities", "summary": "List enabled Odoo resources and allowed fields before operating", "responses": {"200": {"description": "Capabilities"}}}},
            "/records/{resource}": {
                "get": {"operationId": "listRecords", "summary": "List records from a permitted business resource", "parameters": [
                    {"name": "resource", "in": "path", "required": True, "schema": {"$ref": "#/components/schemas/Resource"}},
                    {"name": "filters", "in": "query", "description": "JSON object with allowed field filters", "schema": {"type": "string"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 100}},
                ], "responses": {"200": {"description": "Records"}}},
                "post": {"operationId": "createRecord", "summary": "Create a permitted business record or activity", "parameters": [{"name": "resource", "in": "path", "required": True, "schema": {"$ref": "#/components/schemas/Resource"}}], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["values"], "properties": {"values": {"$ref": "#/components/schemas/Values"}}}}}}, "responses": {"200": {"description": "Created"}}},
            },
            "/records/{resource}/{record_id}": {
                "get": {"operationId": "getRecord", "summary": "Read one permitted record", "parameters": [resource_parameter, record_id_parameter], "responses": {"200": {"description": "Record"}}},
                "patch": {"operationId": "updateRecord", "summary": "Update one permitted record", "parameters": [resource_parameter, record_id_parameter], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["values"], "properties": {"values": {"$ref": "#/components/schemas/Values"}}}}}}, "responses": {"200": {"description": "Updated"}}},
                "delete": {"operationId": "requestDelete", "summary": "Request deletion; this only creates a pending confirmation", "parameters": [resource_parameter, record_id_parameter], "responses": {"200": {"description": "Pending confirmation"}}},
            },
            "/records/{resource}/{record_id}/actions/{action}": {"post": {"operationId": "requestSensitiveAction", "summary": "Request quotation confirmation, invoice posting, or stock-transfer validation; does not execute yet", "parameters": [resource_parameter, record_id_parameter, {"name": "action", "in": "path", "required": True, "schema": {"type": "string", "enum": ["confirm", "post", "validate"]}}], "responses": {"200": {"description": "Pending confirmation"}}}},
            "/confirmations": {"get": {"operationId": "listPendingConfirmations", "summary": "List operations waiting for explicit user confirmation", "responses": {"200": {"description": "Pending confirmations"}}}},
            "/confirmations/{token}/confirm": {"post": {"operationId": "confirmPendingOperation", "summary": "Execute a pending operation only after the user explicitly confirms it", "parameters": [{"name": "token", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Executed"}}}},
            "/audit": {"get": {"operationId": "listAuditLog", "summary": "Read the recent GPT operation audit log", "responses": {"200": {"description": "Audit log"}}}},
        },
    }
