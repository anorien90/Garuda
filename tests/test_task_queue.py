"""
Tests for the Persistent Task Queue Service.

Tests cover:
- Task submission and retrieval
- Task status transitions
- Queue statistics
- Task cancellation
- Task deletion
- Worker processing
- Stale task recovery
- Sequential execution
"""

import time
import uuid
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from garuda_intel.database.models import Base, Task
from garuda_intel.services.task_queue import TaskQueueService


@pytest.fixture
def memory_store(tmp_path):
    """Create a SQLAlchemy store backed by a temp file for testing.
    
    Using a file-based SQLite (not :memory:) so that the background worker
    thread can access the same data through a separate connection.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    db_path = tmp_path / "test_tasks.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    class MockStore:
        def __init__(self):
            self._Session = Session
        
        def Session(self):
            return self._Session()
    
    return MockStore()


@pytest.fixture
def task_queue(memory_store):
    """Create a TaskQueueService with in-memory store."""
    tq = TaskQueueService(memory_store, poll_interval=0.1)
    yield tq
    tq.stop_worker()


class TestTaskSubmission:
    """Test task submission."""
    
    def test_submit_returns_task_id(self, task_queue):
        task_id = task_queue.submit("agent_reflect", {"dry_run": True})
        assert task_id is not None
        assert len(task_id) == 36  # UUID format

    def test_submit_stores_task_in_db(self, task_queue):
        task_id = task_queue.submit("agent_reflect", {"target": "test"}, priority=5)
        task = task_queue.get_task(task_id)
        assert task is not None
        assert task["task_type"] == "agent_reflect"
        assert task["status"] == "pending"
        assert task["priority"] == 5
        assert task["params"]["target"] == "test"

    def test_submit_multiple_tasks(self, task_queue):
        ids = [task_queue.submit("agent_reflect") for _ in range(5)]
        assert len(set(ids)) == 5  # All unique IDs
        tasks = task_queue.list_tasks()
        assert len(tasks) == 5


class TestTaskRetrieval:
    """Test task retrieval and listing."""
    
    def test_get_task_by_id(self, task_queue):
        task_id = task_queue.submit("agent_chat", {"question": "test?"})
        task = task_queue.get_task(task_id)
        assert task["id"] == task_id
        assert task["task_type"] == "agent_chat"

    def test_get_nonexistent_task(self, task_queue):
        assert task_queue.get_task(str(uuid.uuid4())) is None

    def test_get_invalid_id(self, task_queue):
        assert task_queue.get_task("not-a-uuid") is None

    def test_list_all_tasks(self, task_queue):
        task_queue.submit("agent_reflect")
        task_queue.submit("agent_chat")
        tasks = task_queue.list_tasks()
        assert len(tasks) == 2

    def test_list_filter_by_status(self, task_queue):
        task_queue.submit("agent_reflect")
        task_queue.submit("agent_chat")
        tasks = task_queue.list_tasks(status="pending")
        assert len(tasks) == 2
        tasks = task_queue.list_tasks(status="completed")
        assert len(tasks) == 0

    def test_list_filter_by_type(self, task_queue):
        task_queue.submit("agent_reflect")
        task_queue.submit("agent_chat")
        task_queue.submit("agent_reflect")
        tasks = task_queue.list_tasks(task_type="agent_reflect")
        assert len(tasks) == 2


class TestTaskCancellation:
    """Test task cancellation."""
    
    def test_cancel_pending_task(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        result = task_queue.cancel(task_id)
        assert result["success"] is True
        task = task_queue.get_task(task_id)
        assert task["status"] == "cancelled"

    def test_cancel_nonexistent_task(self, task_queue):
        result = task_queue.cancel(str(uuid.uuid4()))
        assert "error" in result

    def test_cancel_already_completed(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        # Manually complete it
        task_uuid = uuid.UUID(task_id)
        with task_queue.store.Session() as session:
            task = session.get(Task, task_uuid)
            task.status = "completed"
            session.commit()
        result = task_queue.cancel(task_id)
        assert "error" in result

    def test_cancel_invalid_id(self, task_queue):
        result = task_queue.cancel("not-a-uuid")
        assert "error" in result


class TestTaskDeletion:
    """Test task deletion."""
    
    def test_delete_completed_task(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        # Complete the task first
        task_uuid = uuid.UUID(task_id)
        with task_queue.store.Session() as session:
            task = session.get(Task, task_uuid)
            task.status = "completed"
            session.commit()
        result = task_queue.delete_task(task_id)
        assert result["success"] is True
        assert task_queue.get_task(task_id) is None

    def test_delete_pending_task_fails(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        result = task_queue.delete_task(task_id)
        assert "error" in result

    def test_delete_nonexistent_task(self, task_queue):
        result = task_queue.delete_task(str(uuid.uuid4()))
        assert "error" in result


class TestQueueStats:
    """Test queue statistics."""
    
    def test_empty_stats(self, task_queue):
        stats = task_queue.get_queue_stats()
        assert stats["total"] == 0
        assert stats["counts"]["pending"] == 0

    def test_stats_with_tasks(self, task_queue):
        task_queue.submit("agent_reflect")
        task_queue.submit("agent_chat")
        stats = task_queue.get_queue_stats()
        assert stats["counts"]["pending"] == 2
        assert stats["total"] == 2


class TestProgressUpdate:
    """Test progress updates."""
    
    def test_update_progress(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        # Mark as running first
        task_uuid = uuid.UUID(task_id)
        with task_queue.store.Session() as session:
            task = session.get(Task, task_uuid)
            task.status = "running"
            session.commit()
        
        task_queue.update_progress(task_id, 0.5, "Halfway done")
        task = task_queue.get_task(task_id)
        assert task["progress"] == 0.5
        assert task["progress_message"] == "Halfway done"


class TestIsCancelled:
    """Test cooperative cancellation check."""
    
    def test_not_cancelled(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        assert task_queue.is_cancelled(task_id) is False

    def test_is_cancelled(self, task_queue):
        task_id = task_queue.submit("agent_reflect")
        task_queue.cancel(task_id)
        assert task_queue.is_cancelled(task_id) is True


class TestWorkerExecution:
    """Test background worker task execution."""
    
    def test_worker_processes_task(self, task_queue):
        """Test that worker processes a task with a registered handler."""
        result_holder = {}
        
        def handler(task_id, params):
            result_holder["executed"] = True
            result_holder["task_id"] = task_id
            return {"answer": "done"}
        
        task_queue.register_handler("test_task", handler)
        task_id = task_queue.submit("test_task", {"key": "value"})
        
        task_queue.start_worker()
        time.sleep(1)  # Give worker time to process
        task_queue.stop_worker()
        
        assert result_holder.get("executed") is True
        task = task_queue.get_task(task_id)
        assert task["status"] == "completed"
        assert task["result"]["answer"] == "done"

    def test_worker_handles_failure(self, task_queue):
        """Test that worker marks task as failed on exception."""
        def handler(task_id, params):
            raise ValueError("Something broke")
        
        task_queue.register_handler("fail_task", handler)
        task_id = task_queue.submit("fail_task")
        
        task_queue.start_worker()
        time.sleep(1)
        task_queue.stop_worker()
        
        task = task_queue.get_task(task_id)
        assert task["status"] == "failed"
        assert "Something broke" in task["error"]

    def test_worker_processes_sequentially(self, task_queue):
        """Test that tasks are processed one at a time."""
        execution_order = []
        
        def handler(task_id, params):
            execution_order.append(params.get("order"))
            time.sleep(0.1)
            return {"order": params.get("order")}
        
        task_queue.register_handler("seq_task", handler)
        task_queue.submit("seq_task", {"order": 1})
        task_queue.submit("seq_task", {"order": 2})
        task_queue.submit("seq_task", {"order": 3})
        
        task_queue.start_worker()
        time.sleep(2)
        task_queue.stop_worker()
        
        assert len(execution_order) == 3
        assert execution_order == [1, 2, 3]

    def test_worker_no_handler(self, task_queue):
        """Test task with no handler is marked as failed."""
        task_id = task_queue.submit("unknown_type")
        
        task_queue.start_worker()
        time.sleep(1)
        task_queue.stop_worker()
        
        task = task_queue.get_task(task_id)
        assert task["status"] == "failed"
        assert "No handler" in task["error"]


class TestStaleRecovery:
    """Test recovery of stale tasks after restart."""
    
    def test_recover_stale_running_tasks(self, memory_store):
        """Test that tasks left running from before restart are marked failed."""
        # Insert a 'running' task simulating a crash
        with memory_store.Session() as session:
            task = Task(
                id=uuid.uuid4(),
                entry_type="task",
                task_type="agent_reflect",
                status="running",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(task)
            session.commit()
            task_id = str(task.id)
        
        # Creating TaskQueueService should recover stale tasks
        tq = TaskQueueService(memory_store, poll_interval=0.1)
        task = tq.get_task(task_id)
        assert task["status"] == "failed"
        assert "Server restarted" in task["error"]


class TestNewTaskHandlers:
    """Test TASK_CHAT and TASK_CRAWL handler registration."""
    
    def test_task_chat_constant_exists(self):
        """Test that TASK_CHAT constant is defined."""
        assert hasattr(TaskQueueService, 'TASK_CHAT')
        assert TaskQueueService.TASK_CHAT == "chat"
    
    def test_task_crawl_constant_exists(self):
        """Test that TASK_CRAWL constant is defined."""
        assert hasattr(TaskQueueService, 'TASK_CRAWL')
        assert TaskQueueService.TASK_CRAWL == "crawl"
    
    def test_can_submit_chat_task(self, task_queue):
        """Test that TASK_CHAT tasks can be submitted."""
        task_id = task_queue.submit(TaskQueueService.TASK_CHAT, {
            "question": "What is AI?",
            "entity": "artificial intelligence"
        })
        assert task_id is not None
        task = task_queue.get_task(task_id)
        assert task["task_type"] == "chat"
        assert task["params"]["question"] == "What is AI?"
    
    def test_can_submit_crawl_task(self, task_queue):
        """Test that TASK_CRAWL tasks can be submitted."""
        task_id = task_queue.submit(TaskQueueService.TASK_CRAWL, {
            "mode": "standard",
            "url": "https://example.com"
        })
        assert task_id is not None
        task = task_queue.get_task(task_id)
        assert task["task_type"] == "crawl"
        assert task["params"]["mode"] == "standard"
    
    def test_can_register_chat_handler(self, task_queue):
        """Test that a handler for TASK_CHAT can be registered."""
        def chat_handler(task_id, params):
            return {"answer": "Test answer", "question": params.get("question")}
        
        task_queue.register_handler(TaskQueueService.TASK_CHAT, chat_handler)
        task_id = task_queue.submit(TaskQueueService.TASK_CHAT, {"question": "test?"})
        
        task_queue.start_worker()
        time.sleep(1)
        task_queue.stop_worker()
        
        task = task_queue.get_task(task_id)
        assert task["status"] == "completed"
        assert task["result"]["answer"] == "Test answer"
    
    def test_can_register_crawl_handler(self, task_queue):
        """Test that a handler for TASK_CRAWL can be registered."""
        def crawl_handler(task_id, params):
            mode = params.get("mode", "standard")
            return {"crawled": True, "mode": mode, "pages": 10}
        
        task_queue.register_handler(TaskQueueService.TASK_CRAWL, crawl_handler)
        task_id = task_queue.submit(TaskQueueService.TASK_CRAWL, {"mode": "intelligent"})
        
        task_queue.start_worker()
        time.sleep(1)
        task_queue.stop_worker()
        
        task = task_queue.get_task(task_id)
        assert task["status"] == "completed"
        assert task["result"]["mode"] == "intelligent"
        assert task["result"]["crawled"] is True
