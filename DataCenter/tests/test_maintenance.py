import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maintenance_list import CircularDoublyLinkedList  # noqa: E402
from maintenance_service import (  # noqa: E402
    DuplicateTaskError,
    InvalidTransitionError,
    MaintenanceService,
    TaskNotFoundError,
    ValidationError,
)
from models import MaintenanceTask  # noqa: E402


def make_task(task_id):
    return MaintenanceTask(
        task_id=task_id,
        title=f"Task {task_id}",
        equipment_name="Rack A",
        equipment_type="SERVER",
        description="Routine inspection",
        priority="MEDIUM",
        assigned_technician="Tech One",
        estimated_minutes=30,
    )


def valid_payload(**overrides):
    payload = {
        "title": "Inspect Rack B",
        "equipment_name": "Rack B",
        "equipment_type": "SERVER",
        "description": "Revisar temperatura y cableado.",
        "priority": "HIGH",
        "assigned_technician": "Ana Ruiz",
        "estimated_minutes": 25,
    }
    payload.update(overrides)
    return payload


def build_list(*task_ids):
    task_list = CircularDoublyLinkedList()
    for task_id in task_ids:
        task_list.append(make_task(task_id))
    return task_list


def forward_ids(task_list):
    return [task.task_id for task in task_list.get_all_tasks()]


def backward_ids(task_list):
    ids = []
    node = task_list.head.prev if task_list.head else None
    for _ in range(task_list.size):
        ids.append(node.task.task_id)
        node = node.prev
    return ids


def count_nodes(task_list):
    if task_list.head is None:
        return 0
    count = 1
    node = task_list.head.next
    while node is not task_list.head:
        count += 1
        node = node.next
        if count > task_list.size + 1:
            break
    return count


class LinkAssertions(unittest.TestCase):
    def assert_structure(self, task_list, expected_ids):
        self.assertEqual(task_list.size, len(expected_ids))
        self.assertEqual(count_nodes(task_list), len(expected_ids))
        self.assertEqual(forward_ids(task_list), expected_ids)
        self.assertEqual(backward_ids(task_list), list(reversed(expected_ids)))
        if expected_ids:
            head = task_list.head
            tail = head.prev
            self.assertIs(tail.next, head)
            self.assertIs(head.prev, tail)
            node = head
            for _ in range(task_list.size):
                self.assertIs(node.next.prev, node)
                self.assertIs(node.prev.next, node)
                node = node.next
        self.assertTrue(task_list.validate_integrity()["valid"])


class CircularDoublyLinkedListTests(LinkAssertions):
    def test_empty_list(self):
        task_list = CircularDoublyLinkedList()
        self.assertIsNone(task_list.head)
        self.assertIsNone(task_list.current)
        self.assertEqual(task_list.size, 0)
        self.assertTrue(task_list.is_empty())
        self.assertIsNone(task_list.next_task())
        self.assertIsNone(task_list.previous_task())
        self.assertEqual(task_list.get_all_tasks(), [])
        report = task_list.validate_integrity()
        self.assertTrue(report["valid"])
        self.assertEqual(report["visited_forward"], 0)

    def test_insert_first_node_points_to_itself(self):
        task_list = build_list("A")
        node = task_list.head
        self.assertIs(node.next, node)
        self.assertIs(node.prev, node)
        self.assertIs(task_list.current, node)
        self.assert_structure(task_list, ["A"])

    def test_prepend(self):
        task_list = build_list("B", "C")
        old_head = task_list.head
        new_node = task_list.prepend(make_task("A"))
        self.assertIs(task_list.head, new_node)
        self.assertIs(new_node.next, old_head)
        self.assertIs(old_head.prev, new_node)
        self.assertEqual(new_node.prev.task.task_id, "C")
        self.assert_structure(task_list, ["A", "B", "C"])

    def test_prepend_on_empty_list(self):
        task_list = CircularDoublyLinkedList()
        task_list.prepend(make_task("A"))
        self.assert_structure(task_list, ["A"])

    def test_append(self):
        task_list = build_list("A", "B")
        new_node = task_list.append(make_task("C"))
        self.assertIs(task_list.head.prev, new_node)
        self.assertIs(new_node.next, task_list.head)
        self.assert_structure(task_list, ["A", "B", "C"])

    def test_insert_after(self):
        task_list = build_list("A", "C")
        node_a = task_list.find("A")
        node_c = task_list.find("C")
        new_node = task_list.insert_after("A", make_task("B"))
        self.assertIs(node_a.next, new_node)
        self.assertIs(new_node.prev, node_a)
        self.assertIs(new_node.next, node_c)
        self.assertIs(node_c.prev, new_node)
        self.assert_structure(task_list, ["A", "B", "C"])

    def test_insert_after_tail_keeps_circularity(self):
        task_list = build_list("A", "B")
        new_node = task_list.insert_after("B", make_task("C"))
        self.assertIs(new_node.next, task_list.head)
        self.assertIs(task_list.head.prev, new_node)
        self.assert_structure(task_list, ["A", "B", "C"])

    def test_insert_after_missing_reference(self):
        task_list = build_list("A")
        self.assertIsNone(task_list.insert_after("X", make_task("B")))
        self.assert_structure(task_list, ["A"])

    def test_forward_navigation_and_wrap(self):
        task_list = build_list("A", "B", "C")
        self.assertEqual(task_list.next_task().task_id, "B")
        self.assertEqual(task_list.next_task().task_id, "C")
        self.assertEqual(task_list.next_task().task_id, "A")
        self.assertIs(task_list.current, task_list.head)

    def test_backward_navigation_and_wrap(self):
        task_list = build_list("A", "B", "C")
        self.assertEqual(task_list.previous_task().task_id, "C")
        self.assertIs(task_list.current, task_list.head.prev)
        self.assertEqual(task_list.previous_task().task_id, "B")
        self.assertEqual(task_list.previous_task().task_id, "A")

    def test_full_cycle_both_directions(self):
        task_list = build_list("A", "B", "C", "D")
        start = task_list.current
        for _ in range(task_list.size):
            task_list.next_task()
        self.assertIs(task_list.current, start)
        for _ in range(task_list.size):
            task_list.previous_task()
        self.assertIs(task_list.current, start)

    def test_remove_head(self):
        task_list = build_list("A", "B", "C")
        task_list.select("C")
        removed = task_list.remove("A")
        self.assertEqual(removed.task_id, "A")
        self.assertEqual(task_list.head.task.task_id, "B")
        self.assertIs(task_list.head.prev, task_list.find("C"))
        self.assert_structure(task_list, ["B", "C"])

    def test_remove_tail(self):
        task_list = build_list("A", "B", "C")
        task_list.remove("C")
        self.assertIs(task_list.head.prev, task_list.find("B"))
        self.assertIs(task_list.find("B").next, task_list.head)
        self.assert_structure(task_list, ["A", "B"])

    def test_remove_current_selects_next_node(self):
        task_list = build_list("A", "B", "C")
        task_list.select("B")
        task_list.remove("B")
        self.assertEqual(task_list.get_current_task().task_id, "C")
        self.assert_structure(task_list, ["A", "C"])

    def test_remove_current_tail_wraps_to_head(self):
        task_list = build_list("A", "B", "C")
        task_list.select("C")
        task_list.remove("C")
        self.assertIs(task_list.current, task_list.head)

    def test_remove_detaches_node(self):
        task_list = build_list("A", "B")
        node = task_list.find("B")
        task_list.remove("B")
        self.assertIsNone(node.next)
        self.assertIsNone(node.prev)

    def test_remove_only_node(self):
        task_list = build_list("A")
        task_list.remove("A")
        self.assertIsNone(task_list.head)
        self.assertIsNone(task_list.current)
        self.assertEqual(task_list.size, 0)
        self.assertTrue(task_list.validate_integrity()["valid"])

    def test_remove_missing_does_not_change_list(self):
        task_list = build_list("A", "B")
        head, current = task_list.head, task_list.current
        self.assertIsNone(task_list.remove("X"))
        self.assertIs(task_list.head, head)
        self.assertIs(task_list.current, current)
        self.assert_structure(task_list, ["A", "B"])

    def test_find_missing(self):
        self.assertIsNone(build_list("A", "B").find("Z"))
        self.assertIsNone(CircularDoublyLinkedList().find("Z"))

    def test_successive_operations(self):
        task_list = CircularDoublyLinkedList()
        expected = []
        for index in range(1, 9):
            task_list.append(make_task(f"T{index}"))
            expected.append(f"T{index}")
        task_list.prepend(make_task("T0"))
        expected.insert(0, "T0")
        task_list.insert_after("T4", make_task("T4B"))
        expected.insert(expected.index("T4") + 1, "T4B")
        for task_id in ("T0", "T8", "T4", "T6"):
            task_list.remove(task_id)
            expected.remove(task_id)
            self.assert_structure(task_list, expected)
        task_list.append(make_task("T9"))
        expected.append("T9")
        self.assert_structure(task_list, expected)
        for task_id in list(expected):
            task_list.remove(task_id)
        self.assert_structure(task_list, [])
        self.assertIsNone(task_list.head)

    def test_integrity_detects_broken_link(self):
        task_list = build_list("A", "B", "C")
        task_list.find("B").prev = task_list.find("C")
        report = task_list.validate_integrity()
        self.assertFalse(report["valid"])
        self.assertFalse(next(c for c in report["checks"] if c["name"] == "bidirectional_links")["passed"])

    def test_integrity_detects_wrong_size(self):
        task_list = build_list("A", "B", "C")
        task_list.size = 5
        self.assertFalse(task_list.validate_integrity()["valid"])

    def test_integrity_terminates_on_broken_cycle(self):
        task_list = build_list("A", "B", "C")
        task_list.find("C").next = task_list.find("B")
        report = task_list.validate_integrity()
        self.assertFalse(report["valid"])
        self.assertLessEqual(report["visited_forward"], task_list.size + 1)

    def test_link_map_matches_nodes(self):
        task_list = build_list("A", "B", "C")
        task_list.select("B")
        links = task_list.get_link_map()
        self.assertEqual([link["task_id"] for link in links], ["A", "B", "C"])
        self.assertEqual(links[0]["prev_task_id"], "C")
        self.assertEqual(links[2]["next_task_id"], "A")
        self.assertTrue(links[1]["is_current"])
        self.assertTrue(links[0]["is_head"] and links[2]["is_tail"])


class MaintenanceServiceTests(LinkAssertions):
    def setUp(self):
        self.service = MaintenanceService()

    def test_create_positions(self):
        self.service.create_task(valid_payload(task_id="B"))
        self.service.create_task(valid_payload(task_id="A"), position="start")
        self.service.create_task(valid_payload(task_id="D"))
        self.service.create_task(valid_payload(task_id="C"), position="after", after_task_id="B")
        self.assert_structure(self.service.task_list, ["A", "B", "C", "D"])

    def test_generated_ids_are_unique(self):
        first = self.service.create_task(valid_payload())
        second = self.service.create_task(valid_payload())
        self.assertNotEqual(first.task_id, second.task_id)

    def test_duplicate_id_rejected(self):
        self.service.create_task(valid_payload(task_id="MT-1"))
        with self.assertRaises(DuplicateTaskError):
            self.service.create_task(valid_payload(task_id="mt-1"))
        self.assertEqual(self.service.task_list.size, 1)

    def test_validation_errors(self):
        invalid_payloads = [
            valid_payload(estimated_minutes=0),
            valid_payload(estimated_minutes=-5),
            valid_payload(estimated_minutes="abc"),
            valid_payload(estimated_minutes=2.5),
            valid_payload(estimated_minutes=True),
            valid_payload(priority="URGENT"),
            valid_payload(equipment_type="PRINTER"),
            valid_payload(title="  "),
            valid_payload(task_id="bad id!"),
        ]
        for payload in invalid_payloads:
            with self.assertRaises(ValidationError):
                self.service.create_task(payload)
        missing = valid_payload()
        del missing["assigned_technician"]
        with self.assertRaises(ValidationError):
            self.service.create_task(missing)
        self.assertTrue(self.service.task_list.is_empty())

    def test_invalid_after_reference(self):
        self.service.create_task(valid_payload(task_id="A"))
        with self.assertRaises(TaskNotFoundError):
            self.service.create_task(valid_payload(task_id="B"), position="after", after_task_id="X")
        self.assertEqual(self.service.task_list.size, 1)

    def test_missing_task_errors(self):
        for action in (self.service.get_task, self.service.delete_task, self.service.start_task):
            with self.assertRaises(TaskNotFoundError):
                action("NOPE")
        with self.assertRaises(TaskNotFoundError):
            self.service.move_to_next_task()

    def test_update_task(self):
        self.service.create_task(valid_payload(task_id="A"))
        updated = self.service.update_task("A", {"priority": "critical", "estimated_minutes": "40"})
        self.assertEqual(updated.priority, "CRITICAL")
        self.assertEqual(updated.estimated_minutes, 40)
        with self.assertRaises(ValidationError):
            self.service.update_task("A", {"estimated_minutes": 0})
        with self.assertRaises(ValidationError):
            self.service.update_task("A", {"status": "COMPLETED"})

    def test_state_transitions(self):
        self.service.create_task(valid_payload(task_id="A"))
        with self.assertRaises(InvalidTransitionError):
            self.service.complete_task("A")
        self.assertEqual(self.service.start_task("A").status, "IN_PROGRESS")
        with self.assertRaises(InvalidTransitionError):
            self.service.start_task("A")
        self.assertEqual(self.service.block_task("A", "Falta repuesto de ventilador").status, "BLOCKED")
        with self.assertRaises(InvalidTransitionError):
            self.service.complete_task("A")
        with self.assertRaises(InvalidTransitionError):
            self.service.start_task("A")
        self.assertEqual(self.service.unblock_task("A").status, "PENDING")
        self.assertEqual(self.service.get_task("A").block_reason, "")
        self.service.start_task("A")
        self.assertEqual(self.service.complete_task("A").status, "COMPLETED")
        with self.assertRaises(InvalidTransitionError):
            self.service.block_task("A", "Motivo válido")

    def test_block_requires_reason(self):
        self.service.create_task(valid_payload(task_id="A"))
        with self.assertRaises(ValidationError):
            self.service.block_task("A", "")
        self.assertEqual(self.service.get_task("A").status, "PENDING")

    def test_demo_load_is_idempotent(self):
        first = self.service.load_demo_tasks()
        second = self.service.load_demo_tasks()
        self.assertEqual(len(first), 6)
        self.assertEqual(second, [])
        self.assertEqual(self.service.task_list.size, 6)
        self.assertTrue(all(task.source == "DEMO" for task in self.service.get_all_tasks()))

    def test_summary(self):
        self.service.load_demo_tasks()
        self.service.start_task("DEMO-001")
        self.service.block_task("DEMO-002", "Esperando técnico de proveedor")
        summary = self.service.get_maintenance_summary()
        self.assertEqual(summary["total"], 6)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["pending"], 4)
        self.assertEqual(summary["high_priority"], 4)

    def test_snapshot_round_trip_keeps_order_and_current(self):
        self.service.load_demo_tasks()
        self.service.move_to_next_task()
        self.service.move_to_next_task()
        snapshot = json.loads(json.dumps(self.service.to_snapshot()))
        restored = MaintenanceService.from_snapshot(snapshot)
        self.assertEqual(
            [task.task_id for task in restored.get_all_tasks()],
            [task.task_id for task in self.service.get_all_tasks()],
        )
        self.assertEqual(restored.get_current_task().task_id, "DEMO-003")
        self.assertTrue(restored.validate_integrity()["valid"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        import server

        self.api = server
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_store = server.state_store
        server.state_store = server.JsonStateStore(os.path.join(self.temp_dir.name, "state.json"))

    def tearDown(self):
        self.api.state_store = self.original_store
        self.temp_dir.cleanup()

    def call(self, method, path, body=None):
        raw = json.dumps(body).encode("utf-8") if body is not None else b""
        return self.api.handle_request(method, path, raw)

    def test_full_flow(self):
        status, payload = self.call("POST", "/api/demo")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["summary"]["total"], 6)
        status, payload = self.call("POST", "/api/tasks", {"task": valid_payload(task_id="NEW-1"), "position": "after", "after_task_id": "DEMO-001"})
        self.assertEqual(status, 201)
        self.assertEqual(payload["state"]["tasks"][1]["task_id"], "NEW-1")
        status, payload = self.call("POST", "/api/navigation/previous")
        self.assertEqual(payload["data"]["task_id"], "DEMO-006")
        status, payload = self.call("POST", "/api/navigation/next")
        self.assertEqual(payload["data"]["task_id"], "DEMO-001")
        status, payload = self.call("GET", "/api/integrity")
        self.assertTrue(payload["data"]["valid"])
        self.assertEqual(payload["data"]["visited_forward"], 7)
        status, payload = self.call("DELETE", "/api/tasks/NEW-1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["summary"]["total"], 6)

    def test_state_persists_in_json_file(self):
        self.call("POST", "/api/demo")
        self.call("POST", "/api/navigation/next")
        with open(self.api.state_store.file_path, encoding="utf-8") as state_file:
            snapshot = json.load(state_file)
        self.assertEqual(len(snapshot["tasks"]), 6)
        self.assertEqual(snapshot["current_task_id"], "DEMO-002")
        status, payload = self.call("GET", "/api/tasks/current")
        self.assertEqual(payload["data"]["task_id"], "DEMO-002")

    def test_error_codes(self):
        self.assertEqual(self.call("GET", "/api/tasks/NOPE")[0], 404)
        self.assertEqual(self.call("GET", "/api/unknown")[0], 404)
        self.assertEqual(self.call("POST", "/api/tasks", {"task": valid_payload(estimated_minutes=0)})[0], 400)
        self.call("POST", "/api/tasks", {"task": valid_payload(task_id="X1")})
        self.assertEqual(self.call("POST", "/api/tasks", {"task": valid_payload(task_id="X1")})[0], 409)
        self.assertEqual(self.call("POST", "/api/tasks/X1/complete")[0], 409)
        self.assertEqual(self.call("GET", "/api/tasks?status=WRONG")[0], 400)
        status, payload = self.api.handle_request("POST", "/api/tasks", b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(self.call("PATCH", "/api/tasks")[0], 405)

    def test_filters(self):
        self.call("POST", "/api/demo")
        status, payload = self.call("GET", "/api/tasks?priority=CRITICAL")
        self.assertEqual({task["task_id"] for task in payload["data"]}, {"DEMO-002", "DEMO-003"})

    def test_internal_error_hides_trace(self):
        class BrokenStore:
            lock = self.api.state_store.lock

            def load(self):
                raise RuntimeError("secret internal detail")

        self.api.state_store = BrokenStore()
        status, payload = self.call("GET", "/api/state")
        self.assertEqual(status, 500)
        self.assertNotIn("secret", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
