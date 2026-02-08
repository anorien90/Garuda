"""
Task Queue CLI for Garuda Intel.

Provides command-line interface for task queue operations including:
- List tasks (with filtering by status/type)
- Show task details
- Cancel running/pending tasks
- Delete completed/failed tasks
- Show queue statistics
"""

import argparse
import json
import logging
import sys

from ..config import Settings
from ..database.engine import SQLAlchemyStore
from ..database.models import Task
from .task_queue import TaskQueueService


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def get_task_queue(settings: Settings) -> TaskQueueService:
    """Create TaskQueueService from settings."""
    store = SQLAlchemyStore(url=settings.db_url)
    return TaskQueueService(store)


# ============================================================================
# Commands
# ============================================================================

def cmd_list(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """List tasks in the queue."""
    tasks = tq.list_tasks(
        status=args.status,
        task_type=args.type,
        limit=args.limit,
    )
    
    if not tasks:
        print("No tasks found.")
        return
    
    # Header
    print(f"{'ID':<38} {'Type':<22} {'Status':<12} {'Progress':<10} {'Created':<20}")
    print("-" * 102)
    
    for t in tasks:
        task_id = t["id"][:36]
        task_type = (t["task_type"] or "")[:20]
        status = (t["status"] or "")[:10]
        progress = f"{(t.get('progress') or 0) * 100:.0f}%" if t.get("progress") is not None else "-"
        created = (t.get("created_at") or "")[:19]
        print(f"{task_id:<38} {task_type:<22} {status:<12} {progress:<10} {created:<20}")
    
    print(f"\nTotal: {len(tasks)} task(s)")


def cmd_show(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Show details of a specific task."""
    task = tq.get_task(args.task_id)
    if not task:
        print(f"Task not found: {args.task_id}")
        sys.exit(1)
    
    print(json.dumps(task, indent=2, default=str))


def cmd_cancel(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Cancel a task."""
    result = tq.cancel(args.task_id)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Task {args.task_id} cancelled.")


def cmd_delete(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Delete a completed/failed/cancelled task."""
    result = tq.delete_task(args.task_id)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Task {args.task_id} deleted.")


def cmd_stats(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Show queue statistics."""
    stats = tq.get_queue_stats()
    counts = stats.get("counts", {})
    
    print("Task Queue Statistics")
    print("=" * 30)
    print(f"  Pending:    {counts.get('pending', 0)}")
    print(f"  Running:    {counts.get('running', 0)}")
    print(f"  Completed:  {counts.get('completed', 0)}")
    print(f"  Failed:     {counts.get('failed', 0)}")
    print(f"  Cancelled:  {counts.get('cancelled', 0)}")
    print(f"  Total:      {stats.get('total', 0)}")
    print(f"  Worker:     {'active' if stats.get('worker_running') else 'stopped'}")
    if stats.get("current_task_id"):
        print(f"  Current:    {stats['current_task_id']}")


def cmd_clear(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Clear completed/failed/cancelled tasks."""
    tasks = tq.list_tasks(limit=500)
    deleted = 0
    for t in tasks:
        if t["status"] in ("completed", "failed", "cancelled"):
            result = tq.delete_task(t["id"])
            if result.get("success"):
                deleted += 1
    print(f"Deleted {deleted} finished task(s).")


def cmd_submit(tq: TaskQueueService, args: argparse.Namespace) -> None:
    """Submit a new task."""
    params = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            print("Error: --params must be valid JSON")
            sys.exit(1)
    
    task_id = tq.submit(
        task_type=args.task_type,
        params=params,
        priority=args.priority,
    )
    print(f"Task submitted: {task_id}")


# ============================================================================
# Main
# ============================================================================

def main():
    """Entry point for task queue CLI."""
    parser = argparse.ArgumentParser(
        description="Garuda Task Queue CLI - manage persistent async tasks"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--db-url", help="Database URL (overrides env)")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # list command
    sp_list = subparsers.add_parser("list", aliases=["ls"], help="List tasks")
    sp_list.add_argument("-s", "--status", help="Filter by status")
    sp_list.add_argument("-t", "--type", help="Filter by task type")
    sp_list.add_argument("-l", "--limit", type=int, default=50, help="Max results")
    
    # show command
    sp_show = subparsers.add_parser("show", aliases=["get"], help="Show task details")
    sp_show.add_argument("task_id", help="Task ID")
    
    # cancel command
    sp_cancel = subparsers.add_parser("cancel", help="Cancel a task")
    sp_cancel.add_argument("task_id", help="Task ID to cancel")
    
    # delete command
    sp_delete = subparsers.add_parser("delete", aliases=["rm"], help="Delete a task")
    sp_delete.add_argument("task_id", help="Task ID to delete")
    
    # stats command
    subparsers.add_parser("stats", help="Show queue statistics")
    
    # clear command
    subparsers.add_parser("clear", help="Clear finished tasks")
    
    # submit command
    sp_submit = subparsers.add_parser("submit", help="Submit a new task")
    sp_submit.add_argument("task_type", help="Task type (e.g., agent_reflect)")
    sp_submit.add_argument("-p", "--params", help="Task params as JSON string")
    sp_submit.add_argument("--priority", type=int, default=0, help="Task priority")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    logger = setup_logging(args.verbose)
    
    settings = Settings.from_env()
    if args.db_url:
        settings.db_url = args.db_url
    
    tq = get_task_queue(settings)
    
    cmd_map = {
        "list": cmd_list,
        "ls": cmd_list,
        "show": cmd_show,
        "get": cmd_show,
        "cancel": cmd_cancel,
        "delete": cmd_delete,
        "rm": cmd_delete,
        "stats": cmd_stats,
        "clear": cmd_clear,
        "submit": cmd_submit,
    }
    
    handler = cmd_map.get(args.command)
    if handler:
        handler(tq, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
