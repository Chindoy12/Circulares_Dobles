from models import MaintenanceNode


class CircularDoublyLinkedList:
    def __init__(self):
        self.head = None
        self.current = None
        self.size = 0

    def is_empty(self):
        return self.head is None

    def get_tail(self):
        return None if self.is_empty() else self.head.prev

    def append(self, task):
        new_node = MaintenanceNode(task)
        if self.is_empty():
            new_node.next = new_node
            new_node.prev = new_node
            self.head = new_node
            self.current = new_node
        else:
            tail = self.head.prev
            new_node.prev = tail
            new_node.next = self.head
            tail.next = new_node
            self.head.prev = new_node
        self.size += 1
        return new_node

    def prepend(self, task):
        new_node = self.append(task)
        self.head = new_node
        return new_node

    def insert_after(self, task_id, task):
        reference = self.find(task_id)
        if reference is None:
            return None
        new_node = MaintenanceNode(task)
        new_node.prev = reference
        new_node.next = reference.next
        reference.next.prev = new_node
        reference.next = new_node
        self.size += 1
        return new_node

    def find(self, task_id):
        node = self.head
        for _ in range(self.size):
            if node.task.task_id == task_id:
                return node
            node = node.next
        return None

    def remove(self, task_id):
        node = self.find(task_id)
        if node is None:
            return None
        if self.size == 1:
            self.head = None
            self.current = None
        else:
            node.prev.next = node.next
            node.next.prev = node.prev
            if node is self.head:
                self.head = node.next
            if node is self.current:
                self.current = node.next
        node.next = None
        node.prev = None
        self.size -= 1
        return node.task

    def select(self, task_id):
        node = self.find(task_id)
        if node is not None:
            self.current = node
        return node

    def next_task(self):
        if self.is_empty():
            return None
        self.current = self.current.next
        return self.current.task

    def previous_task(self):
        if self.is_empty():
            return None
        self.current = self.current.prev
        return self.current.task

    def get_current_task(self):
        return None if self.current is None else self.current.task

    def get_all_tasks(self):
        tasks = []
        node = self.head
        for _ in range(self.size):
            tasks.append(node.task)
            node = node.next
        return tasks

    def get_link_map(self):
        links = []
        node = self.head
        for position in range(self.size):
            links.append(
                {
                    "position": position,
                    "task_id": node.task.task_id,
                    "prev_task_id": node.prev.task.task_id,
                    "next_task_id": node.next.task.task_id,
                    "is_head": node is self.head,
                    "is_tail": node is self.head.prev,
                    "is_current": node is self.current,
                }
            )
            node = node.next
        return links

    def validate_integrity(self):
        checks = []

        def check(name, passed):
            checks.append({"name": name, "passed": bool(passed)})

        if self.is_empty():
            check("empty_list_consistent", self.current is None and self.size == 0)
            return self._integrity_report(checks, 0, 0)

        visited_ids = set()
        forward_count = 0
        links_ok = True
        current_found = False
        node = self.head
        while forward_count <= self.size:
            if node is None or node.next is None or node.prev is None:
                links_ok = False
                break
            if node.next.prev is not node or node.prev.next is not node:
                links_ok = False
            if node is self.current:
                current_found = True
            visited_ids.add(node.task.task_id)
            forward_count += 1
            node = node.next
            if node is self.head:
                break

        backward_count = 0
        node = self.head
        while backward_count <= self.size and node is not None:
            backward_count += 1
            node = node.prev
            if node is self.head:
                break

        check("bidirectional_links", links_ok)
        check("forward_cycle_returns_to_head", forward_count == self.size and node is self.head)
        check("backward_cycle_returns_to_head", backward_count == self.size)
        check("tail_next_is_head", self.head.prev.next is self.head)
        check("head_prev_is_tail", self.head.prev is self.get_tail())
        check("size_matches_nodes", forward_count == self.size)
        check("current_in_list", current_found)
        check("unique_task_ids", len(visited_ids) == forward_count)
        return self._integrity_report(checks, forward_count, backward_count)

    def _integrity_report(self, checks, forward_count, backward_count):
        return {
            "valid": all(item["passed"] for item in checks),
            "size": self.size,
            "visited_forward": forward_count,
            "visited_backward": backward_count,
            "head_task_id": None if self.head is None else self.head.task.task_id,
            "tail_task_id": None if self.head is None else self.head.prev.task.task_id,
            "current_task_id": None if self.current is None else self.current.task.task_id,
            "checks": checks,
        }
