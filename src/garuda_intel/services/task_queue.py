"""
Persistent Task Queue Service.

Provides a database-backed task queue that:
- Persists tasks across server restarts
- Processes LLM tasks sequentially (protects single Ollama instance)
- Supports task cancellation and progress tracking
- Emits events for UI observability
"""

import logging
import threading
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select, desc, and_

from ..database.models import Task

logger = logging.getLogger(__name__)


class TaskQueueService:
    """
    Persistent task queue with parallel IO and sequential LLM processing.
    
    Tasks are stored in the database so they survive server restarts.
    A background worker thread pool processes IO-bound tasks in parallel
    while protecting the single Ollama LLM instance with serialization.
    """

    # Task type constants
    TASK_AGENT_REFLECT = "agent_reflect"
    TASK_AGENT_EXPLORE = "agent_explore"
    TASK_AGENT_AUTONOMOUS = "agent_autonomous"
    TASK_AGENT_REFLECT_RELATE = "agent_reflect_relate"
    TASK_AGENT_INVESTIGATE = "agent_investigate"
    TASK_AGENT_COMBINED = "agent_combined"
    TASK_AGENT_CHAT = "agent_chat"
    TASK_CHAT = "chat"
    TASK_CRAWL = "crawl"

    # Task category constants
    CATEGORY_IO = "io"
    CATEGORY_LLM = "llm"

    # Limits
    MAX_PROGRESS_MESSAGE_LENGTH = 500
    WORKER_STOP_TIMEOUT_SECONDS = 10

    # Status constants
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    def __init__(self, store, poll_interval: float = 2.0, 
                 max_workers: int = 4):
        """
        Initialize the task queue service.
        
        Args:
            store: SQLAlchemy store instance with Session() context
            poll_interval: Seconds between polling for new tasks
            max_workers: Maximum parallel workers for IO-bound tasks
        """
        self.store = store
        self.poll_interval = poll_interval
        self.max_workers = max_workers
        self._handlers: Dict[str, Callable] = {}
        self._shutdown_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._current_task_id: Optional[str] = None
        self._running_task_ids: set = set()
        self._lock = threading.Lock()
        self._llm_lock = threading.Lock()
        self._active_tasks = 0
        self._executor = None
        
        # Task category mapping - LLM tasks serialized, IO parallel
        self._task_categories: Dict[str, str] = {
            self.TASK_CRAWL: self.CATEGORY_IO,
            self.TASK_AGENT_REFLECT: self.CATEGORY_LLM,
            self.TASK_AGENT_EXPLORE: self.CATEGORY_LLM,
            self.TASK_AGENT_AUTONOMOUS: self.CATEGORY_LLM,
            self.TASK_AGENT_REFLECT_RELATE: self.CATEGORY_LLM,
            self.TASK_AGENT_INVESTIGATE: self.CATEGORY_LLM,
            self.TASK_AGENT_COMBINED: self.CATEGORY_LLM,
            self.TASK_AGENT_CHAT: self.CATEGORY_LLM,
            self.TASK_CHAT: self.CATEGORY_LLM,
        }
        
        # Mark any previously running tasks as failed (restart recovery)
        self._recover_stale_tasks()

    def _recover_stale_tasks(self):
        """Mark tasks that were running when server stopped as failed."""
        try:
            with self.store.Session() as session:
                stale = session.execute(
                    select(Task).where(Task.status == self.STATUS_RUNNING)
                ).scalars().all()
                for task in stale:
                    task.status = self.STATUS_FAILED
                    task.error = "Server restarted while task was running"
                    task.completed_at = datetime.utcnow()
                session.commit()
                if stale:
                    logger.info(f"Recovered {len(stale)} stale tasks after restart")
        except Exception as e:
            logger.warning(f"Failed to recover stale tasks: {e}")

    def register_handler(self, task_type: str, handler: Callable):
        """
        Register a handler function for a task type.
        
        The handler receives (task_id, params_dict) and should return a result dict.
        It can call update_progress() to report progress.
        
        Args:
            task_type: Task type string constant
            handler: Callable that processes the task
        """
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    def submit(
        self,
        task_type: str,
        params: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ) -> str:
        """
        Submit a new task to the queue.
        
        Args:
            task_type: Type of task (use class constants)
            params: Task parameters as a dictionary
            priority: Higher priority tasks are processed first
            
        Returns:
            Task ID as string
        """
        task_id = uuid.uuid4()
        with self.store.Session() as session:
            task = Task(
                id=task_id,
                entry_type="task",
                task_type=task_type,
                status=self.STATUS_PENDING,
                priority=priority,
                params_json=params or {},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(task)
            session.commit()

        task_id_str = str(task_id)
        logger.info(f"Task submitted: {task_id_str} type={task_type} priority={priority}")
        self._emit("task_submitted", f"New {task_type} task queued", {
            "task_id": task_id_str,
            "task_type": task_type,
            "priority": priority,
        })
        return task_id_str

    def cancel(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel a pending or running task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            Result dict with success status
        """
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {"error": "Invalid task ID"}

        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            if not task:
                return {"error": "Task not found"}
            if task.status in (self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_CANCELLED):
                return {"error": f"Task already {task.status}"}
            
            task.status = self.STATUS_CANCELLED
            task.completed_at = datetime.utcnow()
            session.commit()

        self._emit("task_cancelled", f"Task {task_id} cancelled", {"task_id": task_id})
        logger.info(f"Task cancelled: {task_id}")
        return {"success": True, "task_id": task_id, "status": self.STATUS_CANCELLED}

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task details by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task dict or None
        """
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return None

        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            if task:
                return task.to_dict()
        return None

    def list_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List tasks with optional filtering.
        
        Args:
            status: Filter by status
            task_type: Filter by task type
            limit: Maximum number of tasks to return
            
        Returns:
            List of task dicts
        """
        with self.store.Session() as session:
            stmt = select(Task)
            conditions = []
            if status:
                conditions.append(Task.status == status)
            if task_type:
                conditions.append(Task.task_type == task_type)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.order_by(desc(Task.created_at)).limit(limit)
            tasks = session.execute(stmt).scalars().all()
            return [t.to_dict() for t in tasks]

    def update_progress(self, task_id: str, progress: float, message: str = ""):
        """
        Update task progress (called by handler during execution).
        
        Args:
            task_id: Task ID
            progress: Progress value 0.0 to 1.0
            message: Human-readable progress message
        """
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return

        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            if task and task.status == self.STATUS_RUNNING:
                task.progress = min(1.0, max(0.0, progress))
                task.progress_message = message[:self.MAX_PROGRESS_MESSAGE_LENGTH] if message else ""
                session.commit()

        self._emit("task_progress", message or f"Progress: {progress:.0%}", {
            "task_id": task_id,
            "progress": progress,
            "message": message,
        })

    def is_cancelled(self, task_id: str) -> bool:
        """
        Check if a task has been cancelled (for cooperative cancellation).
        
        Args:
            task_id: Task ID to check
            
        Returns:
            True if task is cancelled
        """
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return False

        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            return task is not None and task.status == self.STATUS_CANCELLED

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self.store.Session() as session:
            from sqlalchemy import func
            counts = {}
            for status in [self.STATUS_PENDING, self.STATUS_RUNNING, 
                          self.STATUS_COMPLETED, self.STATUS_FAILED, 
                          self.STATUS_CANCELLED]:
                count = session.execute(
                    select(func.count()).select_from(Task).where(
                        Task.status == status)
                ).scalar()
                counts[status] = count
            
            with self._lock:
                running_ids = list(self._running_task_ids)
                current_id = self._current_task_id
                active = self._active_tasks
            
            return {
                "counts": counts,
                "total": sum(counts.values()),
                "current_task_id": current_id,
                "running_task_ids": running_ids,
                "active_workers": active,
                "max_workers": self.max_workers,
                "worker_running": (self._worker_thread is not None 
                                 and self._worker_thread.is_alive()),
            }

    def delete_task(self, task_id: str) -> Dict[str, Any]:
        """
        Delete a completed/failed/cancelled task.
        
        Args:
            task_id: Task ID to delete
            
        Returns:
            Result dict
        """
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {"error": "Invalid task ID"}

        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            if not task:
                return {"error": "Task not found"}
            if task.status in (self.STATUS_PENDING, self.STATUS_RUNNING):
                return {"error": "Cannot delete active task, cancel it first"}
            
            # Also delete from entries table (parent)
            from ..database.models import BasicDataEntry
            entry = session.get(BasicDataEntry, task_uuid)
            if entry:
                session.delete(entry)
            session.commit()

        return {"success": True, "task_id": task_id}

    # =========================================================================
    # BACKGROUND WORKER
    # =========================================================================

    def start_worker(self):
        """Start the background worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return
        
        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="task-queue-worker",
            daemon=True,
        )
        self._worker_thread.start()
        logger.info("Task queue worker started")

    def stop_worker(self):
        """Stop the background worker thread gracefully."""
        self._shutdown_event.set()
        
        # Shutdown executor if it exists
        if self._executor:
            try:
                # Give executor time to complete current tasks
                self._executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"Error shutting down executor: {e}")
        
        if self._worker_thread:
            self._worker_thread.join(timeout=self.WORKER_STOP_TIMEOUT_SECONDS)
            logger.info("Task queue worker stopped")

    def _worker_loop(self):
        """Main worker loop - dispatches tasks to thread pool."""
        from concurrent.futures import ThreadPoolExecutor
        
        logger.info(
            f"Task queue worker loop started (max_workers={self.max_workers})"
        )
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, 
            thread_name_prefix="tq-worker"
        )
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Check if we can accept more tasks
                    with self._lock:
                        active = self._active_tasks
                    if active >= self.max_workers:
                        self._shutdown_event.wait(self.poll_interval)
                        continue
                    
                    task_dict = self._fetch_next_task()
                    if task_dict:
                        with self._lock:
                            self._active_tasks += 1
                        self._executor.submit(
                            self._execute_task_wrapper, task_dict
                        )
                    else:
                        # No tasks available, wait before polling again
                        self._shutdown_event.wait(self.poll_interval)
                except Exception as e:
                    logger.error(f"Worker loop error: {e}", exc_info=True)
                    self._shutdown_event.wait(self.poll_interval)
        finally:
            self._executor.shutdown(wait=True)
            self._executor = None
        
        logger.info("Task queue worker loop exiting")

    def _fetch_next_task(self) -> Optional[Dict[str, Any]]:
        """Fetch the next pending task (highest priority, oldest first)."""
        with self.store.Session() as session:
            task = session.execute(
                select(Task)
                .where(Task.status == self.STATUS_PENDING)
                .order_by(desc(Task.priority), Task.created_at)
                .limit(1)
            ).scalar_one_or_none()
            
            if task:
                task.status = self.STATUS_RUNNING
                task.started_at = datetime.utcnow()
                session.commit()
                return task.to_dict()
        return None

    def _execute_task_wrapper(self, task_dict: Dict[str, Any]):
        """Wrapper that handles LLM serialization and active task tracking."""
        task_type = task_dict["task_type"]
        category = self._task_categories.get(task_type, self.CATEGORY_LLM)
        
        try:
            if category == self.CATEGORY_LLM:
                with self._llm_lock:
                    self._execute_task(task_dict)
            else:
                self._execute_task(task_dict)
        finally:
            with self._lock:
                self._active_tasks -= 1

    def _execute_task(self, task_dict: Dict[str, Any]):
        """Execute a single task using the registered handler."""
        task_id = task_dict["id"]
        task_type = task_dict["task_type"]

        with self._lock:
            self._running_task_ids.add(task_id)
            # Update current_task_id to one of the running tasks
            if not self._current_task_id:
                self._current_task_id = task_id

        handler = self._handlers.get(task_type)
        if not handler:
            self._complete_task(
                task_id, error=f"No handler for task type: {task_type}"
            )
            with self._lock:
                self._running_task_ids.discard(task_id)
                if not self._running_task_ids:
                    self._current_task_id = None
                elif self._current_task_id == task_id:
                    self._current_task_id = (next(iter(self._running_task_ids)) 
                                            if self._running_task_ids else None)
            return

        self._emit("task_started", f"Processing {task_type} task", {
            "task_id": task_id, "task_type": task_type
        })
        logger.info(f"Executing task {task_id} type={task_type}")

        try:
            result = handler(task_id, task_dict.get("params") or {})
            
            # Check if task was cancelled during execution
            if self.is_cancelled(task_id):
                logger.info(f"Task {task_id} was cancelled during execution")
                return
            
            self._complete_task(task_id, result=result)
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            self._complete_task(task_id, error=str(e))
        finally:
            with self._lock:
                self._running_task_ids.discard(task_id)
                if not self._running_task_ids:
                    self._current_task_id = None
                elif self._current_task_id == task_id:
                    # Pick another running task as current
                    self._current_task_id = (next(iter(self._running_task_ids))
                                            if self._running_task_ids else None)

    def _complete_task(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Mark a task as completed or failed."""
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return

        status = self.STATUS_FAILED if error else self.STATUS_COMPLETED
        with self.store.Session() as session:
            task = session.get(Task, task_uuid)
            if task and task.status != self.STATUS_CANCELLED:
                task.status = status
                task.result_json = result
                task.error = error
                task.progress = 1.0 if not error else task.progress
                task.completed_at = datetime.utcnow()
                session.commit()

        msg = f"Task {task_id} {status}" + (f": {error}" if error else "")
        self._emit(f"task_{status}", msg, {
            "task_id": task_id, "status": status, "error": error,
        })
        logger.log(logging.ERROR if error else logging.INFO, msg)

    def _emit(self, step: str, message: str, payload: Optional[Dict] = None):
        """Emit event for UI observability."""
        try:
            from ..webapp.services.event_system import emit_event
            emit_event(step, message, payload=payload)
        except Exception:
            pass  # Event system may not be initialized during testing
