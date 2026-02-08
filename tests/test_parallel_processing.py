"""
Tests for parallel processing enhancements.

Verify that:
1. Task queue processes IO tasks in parallel
2. Task queue serializes LLM tasks
3. Explorer parallelizes HTTP fetching
4. Seed discovery parallelizes searches
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from garuda_intel.services.task_queue import TaskQueueService
from garuda_intel.database.models import Base


@pytest.fixture
def memory_store(tmp_path):
    """Create a SQLAlchemy store backed by a temp file for testing.
    
    Using a file-based SQLite (not :memory:) so that the background worker
    thread can access the same data through a separate connection.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    db_path = tmp_path / "test_tasks_parallel.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    class MockStore:
        def __init__(self):
            self._Session = Session
        
        def Session(self):
            return self._Session()
    
    return MockStore()


class TestTaskQueueParallelism:
    """Test parallel task execution in TaskQueueService."""
    
    @pytest.fixture
    def queue_service(self, memory_store):
        """Create task queue service with multiple workers."""
        service = TaskQueueService(
            memory_store, poll_interval=0.5, max_workers=3
        )
        yield service
        service.stop_worker()
    
    def test_task_queue_has_parallel_fields(self, queue_service):
        """Verify task queue has new parallel processing fields."""
        assert hasattr(queue_service, 'max_workers')
        assert hasattr(queue_service, '_llm_lock')
        assert hasattr(queue_service, '_active_tasks')
        assert hasattr(queue_service, '_running_task_ids')
        assert hasattr(queue_service, '_task_categories')
        assert hasattr(queue_service, 'CATEGORY_IO')
        assert hasattr(queue_service, 'CATEGORY_LLM')
    
    def test_task_categories_configured(self, queue_service):
        """Verify task categories are correctly configured."""
        # CRAWL should be IO-bound
        assert queue_service._task_categories[
            queue_service.TASK_CRAWL
        ] == queue_service.CATEGORY_IO
        
        # LLM tasks should be LLM-bound
        assert queue_service._task_categories[
            queue_service.TASK_CHAT
        ] == queue_service.CATEGORY_LLM
        assert queue_service._task_categories[
            queue_service.TASK_AGENT_REFLECT
        ] == queue_service.CATEGORY_LLM
    
    def test_queue_stats_includes_parallel_info(self, queue_service):
        """Verify queue stats includes parallel worker info."""
        stats = queue_service.get_queue_stats()
        assert 'max_workers' in stats
        assert 'active_workers' in stats
        assert 'running_task_ids' in stats
        assert stats['max_workers'] == 3
        assert stats['active_workers'] == 0
        assert stats['running_task_ids'] == []
    
    def test_io_tasks_can_run_in_parallel(self, queue_service):
        """Verify IO tasks can execute in parallel."""
        execution_times = {}
        execution_lock = threading.Lock()
        
        def io_handler(task_id, params):
            start = time.time()
            time.sleep(0.3)  # Simulate IO wait
            with execution_lock:
                execution_times[task_id] = (start, time.time())
            return {"result": "done"}
        
        queue_service.register_handler(
            queue_service.TASK_CRAWL, io_handler
        )
        
        # Submit 3 IO tasks
        task_ids = []
        for i in range(3):
            task_id = queue_service.submit(
                queue_service.TASK_CRAWL, 
                {"index": i}
            )
            task_ids.append(task_id)
        
        # Start worker
        queue_service.start_worker()
        
        # Wait for all tasks to complete
        timeout = time.time() + 5
        while time.time() < timeout:
            stats = queue_service.get_queue_stats()
            if stats['counts']['completed'] == 3:
                break
            time.sleep(0.1)
        
        # Check that tasks ran in parallel (overlapping time windows)
        assert len(execution_times) == 3
        
        # If tasks ran sequentially, total time would be ~0.9s
        # If parallel, should be ~0.3s (with overhead)
        # Check for overlap: at least 2 tasks should have overlapping execution
        starts_ends = sorted(execution_times.values())
        overlaps = 0
        for i in range(len(starts_ends) - 1):
            if starts_ends[i][1] > starts_ends[i+1][0]:
                overlaps += 1
        
        # At least one pair should overlap if running in parallel
        assert overlaps >= 1, "Tasks should run in parallel"
    
    def test_llm_tasks_are_serialized(self, queue_service):
        """Verify LLM tasks are serialized even with multiple workers."""
        execution_order = []
        execution_lock = threading.Lock()
        active_count = []
        
        def llm_handler(task_id, params):
            with execution_lock:
                execution_order.append(('start', task_id))
                # Track how many tasks are active simultaneously
                active = len([x for x in execution_order 
                             if x[0] == 'start']) - len(
                                 [x for x in execution_order 
                                  if x[0] == 'end'])
                active_count.append(active)
            
            time.sleep(0.2)  # Simulate LLM processing
            
            with execution_lock:
                execution_order.append(('end', task_id))
            return {"result": "done"}
        
        queue_service.register_handler(
            queue_service.TASK_CHAT, llm_handler
        )
        
        # Submit 3 LLM tasks
        for i in range(3):
            queue_service.submit(queue_service.TASK_CHAT, {"index": i})
        
        queue_service.start_worker()
        
        # Wait for completion
        timeout = time.time() + 5
        while time.time() < timeout:
            stats = queue_service.get_queue_stats()
            if stats['counts']['completed'] == 3:
                break
            time.sleep(0.1)
        
        # Verify only one LLM task was active at a time
        # (max active count should be 1)
        assert max(active_count) == 1, "LLM tasks should be serialized"


class TestExplorerParallelFetch:
    """Test parallel HTTP fetching in IntelligentExplorer."""
    
    def test_explorer_has_max_fetch_workers(self):
        """Verify explorer has max_fetch_workers parameter."""
        from garuda_intel.explorer.engine import IntelligentExplorer
        from garuda_intel.types.entity import EntityProfile, EntityType
        
        profile = EntityProfile(
            name="Test", 
            entity_type=EntityType.COMPANY
        )
        explorer = IntelligentExplorer(
            profile=profile,
            use_selenium=False,
            max_fetch_workers=10
        )
        
        assert hasattr(explorer, 'max_fetch_workers')
        assert explorer.max_fetch_workers == 10


class TestSeedDiscoveryParallel:
    """Test parallel search in seed discovery."""
    
    def test_collect_candidates_uses_threadpool(self):
        """Verify collect_candidates uses ThreadPoolExecutor."""
        from garuda_intel.search.seed_discovery import collect_candidates
        
        # Check function source contains ThreadPoolExecutor
        import inspect
        source = inspect.getsource(collect_candidates)
        assert 'ThreadPoolExecutor' in source
        assert 'as_completed' in source
    
    def test_collect_candidates_simple_uses_threadpool(self):
        """Verify collect_candidates_simple uses ThreadPoolExecutor."""
        from garuda_intel.search.seed_discovery import (
            collect_candidates_simple
        )
        
        # Check function source contains ThreadPoolExecutor
        import inspect
        source = inspect.getsource(collect_candidates_simple)
        assert 'ThreadPoolExecutor' in source
        assert 'as_completed' in source


class TestAdaptiveCrawlerParallel:
    """Test parallel seed collection in AdaptiveCrawlerService."""
    
    def test_intelligent_crawl_uses_threadpool(self):
        """Verify intelligent_crawl uses ThreadPoolExecutor."""
        from garuda_intel.services.adaptive_crawler import (
            AdaptiveCrawlerService
        )
        
        # Check method source contains ThreadPoolExecutor
        import inspect
        source = inspect.getsource(
            AdaptiveCrawlerService.intelligent_crawl
        )
        assert 'ThreadPoolExecutor' in source
        assert 'as_completed' in source
