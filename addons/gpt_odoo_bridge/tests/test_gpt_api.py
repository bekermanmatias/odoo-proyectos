from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.gpt_odoo_bridge.services.api_service import GptApiError, GptApiService


@tagged("post_install", "-at_install")
class TestGptApi(TransactionCase):
    def test_api_key_is_required(self):
        with patch.dict("os.environ", {"GPT_ODOO_API_KEY": "test-key"}, clear=False):
            GptApiService.assert_authorized("Bearer test-key")
            with self.assertRaises(GptApiError) as error:
                GptApiService.assert_authorized("Bearer wrong-key")
        self.assertEqual(error.exception.status, 401)

    def test_projects_are_restricted_and_audited(self):
        project = self.env["project.project"].create({"name": "GPT test project"})
        result = GptApiService.get_record(self.env, "projects", project.id)
        self.assertEqual(result["record"]["name"], "GPT test project")

        audit = GptApiService.audit(
            self.env, correlation_id="test-correlation", endpoint="/test", operation="read",
            status="success", resource="projects", record_ids=[project.id], request_data={}, response_data=result,
        )
        self.assertEqual(audit.technical_user_id, self.env.user)

    def test_tasks_can_use_existing_tags_and_priority(self):
        project = self.env["project.project"].create({"name": "Task tag project"})
        tag = self.env["project.tags"].create({"name": "Backend"})
        task = GptApiService.create_record(self.env, "tasks", {
            "name": "Urgent tagged task", "project_id": project.id,
            "tag_ids": [tag.id], "priority": "3",
        })["record"]
        self.assertEqual(task["priority"], "3")
        self.assertEqual(task["tag_ids"], [tag.id])

    def test_task_description_preserves_semantic_html(self):
        project = self.env["project.project"].create({"name": "Rich description project"})
        description = (
            "<h2>Objetivo</h2><p>Crear una inscripción clara.</p>"
            "<h2>Alcance</h2><ul><li>Formulario</li><li>Validación</li></ul>"
            "<h2>Criterios de aceptación</h2><p><strong>Sin errores</strong> al enviar.</p>"
        )
        task = GptApiService.create_record(self.env, "tasks", {
            "name": "Task with rich description", "project_id": project.id,
            "description": description,
        })["record"]
        self.assertIn("<h2>Objetivo</h2>", task["description"])
        self.assertIn("<ul><li>Formulario</li><li>Validación</li></ul>", task["description"])
        self.assertIn("<strong>Sin errores</strong>", task["description"])

    def test_task_stages_can_be_linked_to_one_project(self):
        project = self.env["project.project"].create({"name": "Rock and Gol stage project"})
        stage = GptApiService.create_record(self.env, "task-stages", {
            "name": "Backlog", "sequence": 1, "project_ids": [project.id],
        })["record"]
        self.assertEqual(stage["project_ids"], [project.id])

        stages = GptApiService.list_records(
            self.env, "task-stages", {"project_ids": project.id}, limit=100,
        )["records"]
        self.assertTrue(any(row["id"] == stage["id"] for row in stages))

    def test_delete_requires_confirmation(self):
        project = self.env["project.project"].create({"name": "Delete after confirmation"})
        pending = GptApiService.request_confirmation(
            self.env, correlation_id="test-confirm", endpoint="/test", resource="projects",
            record_id=project.id, operation="delete",
        )
        self.assertTrue(project.exists())
        result = GptApiService.execute_confirmation(self.env, pending["confirmation_id"])
        self.assertTrue(result["deleted"])
        self.assertFalse(project.exists())
