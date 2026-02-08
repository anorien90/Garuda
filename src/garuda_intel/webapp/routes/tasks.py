"""Task Queue API routes for persistent async task management."""

import logging
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event

bp_tasks = Blueprint('tasks', __name__, url_prefix='/api/tasks')
logger = logging.getLogger(__name__)


def init_task_routes(api_key_required, task_queue):
    """Initialize task queue routes.
    
    Args:
        api_key_required: Auth decorator
        task_queue: TaskQueueService instance
    """

    @bp_tasks.get("/")
    @api_key_required
    def api_list_tasks():
        """
        List tasks with optional filtering.
        
        Query params:
            status: Filter by status (pending, running, completed, failed, cancelled)
            task_type: Filter by task type
            limit: Max results (default 50)
        """
        status = request.args.get("status")
        task_type = request.args.get("task_type")
        limit = int(request.args.get("limit", 50))
        
        tasks = task_queue.list_tasks(status=status, task_type=task_type, limit=limit)
        return jsonify({"tasks": tasks})

    @bp_tasks.get("/stats")
    @api_key_required
    def api_queue_stats():
        """Get task queue statistics."""
        return jsonify(task_queue.get_queue_stats())

    @bp_tasks.get("/<task_id>")
    @api_key_required
    def api_get_task(task_id):
        """Get a specific task by ID."""
        task = task_queue.get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    @bp_tasks.post("/")
    @api_key_required
    def api_submit_task():
        """
        Submit a new task to the queue.
        
        Request body (JSON):
            task_type: Type of task (required)
            params: Task parameters (optional)
            priority: Task priority, higher = more urgent (optional, default 0)
        """
        body = request.get_json(silent=True) or {}
        
        task_type = body.get("task_type", "").strip()
        if not task_type:
            return jsonify({"error": "task_type required"}), 400
        
        params = body.get("params", {})
        priority = int(body.get("priority", 0))
        
        task_id = task_queue.submit(
            task_type=task_type,
            params=params,
            priority=priority,
        )
        
        return jsonify({
            "task_id": task_id,
            "status": "pending",
            "message": f"Task {task_type} submitted to queue",
        }), 201

    @bp_tasks.post("/<task_id>/cancel")
    @api_key_required
    def api_cancel_task(task_id):
        """Cancel a pending or running task."""
        result = task_queue.cancel(task_id)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    @bp_tasks.delete("/<task_id>")
    @api_key_required
    def api_delete_task(task_id):
        """Delete a completed/failed/cancelled task."""
        result = task_queue.delete_task(task_id)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    return bp_tasks
