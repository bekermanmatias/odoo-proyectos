from odoo import fields, models


class GptApiAudit(models.Model):
    _name = "gpt.api.audit"
    _description = "GPT API audit log"
    _order = "create_date desc, id desc"

    correlation_id = fields.Char(required=True, index=True)
    endpoint = fields.Char(required=True)
    operation = fields.Char(required=True)
    resource = fields.Char()
    record_ids = fields.Char()
    status = fields.Selection(
        [("success", "Success"), ("pending", "Pending confirmation"), ("error", "Error")],
        required=True,
        index=True,
    )
    request_summary = fields.Text()
    response_summary = fields.Text()
    technical_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")


class GptApiConfirmation(models.Model):
    _name = "gpt.api.confirmation"
    _description = "GPT API pending confirmation"
    _order = "create_date desc, id desc"

    token = fields.Char(required=True, index=True, copy=False)
    operation = fields.Char(required=True)
    resource = fields.Char(required=True)
    record_id = fields.Integer()
    payload_json = fields.Text(required=True)
    summary = fields.Text(required=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("executed", "Executed"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="pending",
        index=True,
    )
    expires_at = fields.Datetime(required=True, index=True)
    technical_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    audit_id = fields.Many2one("gpt.api.audit", required=True, ondelete="cascade")
