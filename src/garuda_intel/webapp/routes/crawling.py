"""Crawling API routes."""

import logging
from flask import Blueprint, jsonify, request
from ..services.event_system import emit_event
from ...search import run_crawl_api
from ...database.models import Entity


bp = Blueprint('crawling', __name__, url_prefix='/api/crawl')
logger = logging.getLogger(__name__)


def _get_task_queue():
    """Get the task queue service from the app context (lazy import to avoid circular imports)."""
    try:
        from ..app import task_queue
        return task_queue
    except Exception:
        return None


def init_routes(api_key_required, settings, store, llm, entity_crawler, crawl_learner, gap_analyzer, adaptive_crawler):
    """Initialize routes with required dependencies."""
    
    @bp.post("/")
    @api_key_required
    def api_crawl():
        body = request.get_json(silent=True) or {}
        
        # Support queued execution
        if body.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_CRAWL, body)
                return jsonify({"task_id": task_id, "status": "pending", "message": "Crawl task queued"}), 202
        
        emit_event("crawl", "start", payload={"body": body})
        try:
            result = run_crawl_api(body)
            emit_event("crawl", "done", payload={"status": "ok"})
            return jsonify(result)
        except ValueError as e:
            emit_event("crawl", f"bad request: {e}", level="warning")
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            emit_event("crawl", f"failed: {e}", level="error")
            logger.exception("Crawl failed")
            return jsonify({"error": f"crawl failed: {e}"}), 500
    
    @bp.get("/learning/stats")
    @api_key_required
    def api_crawl_learning_stats():
        """Get crawl learning statistics."""
        try:
            domains = request.args.get("domains", "").split(",")
            domains = [d.strip() for d in domains if d.strip()]
            
            stats = {
                "domain_reliability": {},
                "successful_patterns": {}
            }
            
            for domain in domains[:20]:
                reliability = crawl_learner.get_domain_reliability(domain)
                if reliability > 0:
                    stats["domain_reliability"][domain] = reliability
            
            for entity_type in ["PERSON", "COMPANY", "NEWS", "TOPIC"]:
                patterns = crawl_learner.get_successful_patterns(entity_type)
                if patterns:
                    stats["successful_patterns"][entity_type] = patterns[:10]
            
            return jsonify(stats)
        except Exception as e:
            logger.exception("Crawl learning stats failed")
            return jsonify({"error": str(e)}), 500
    
    @bp.route("/intelligent", methods=["POST"])
    @api_key_required
    def api_intelligent_crawl():
        """Start an intelligent, gap-aware crawl for an entity."""
        data = request.get_json() or {}
        
        entity_name = data.get("entity_name", "").strip()
        if not entity_name:
            return jsonify({"error": "entity_name is required"}), 400
        
        entity_type = data.get("entity_type")
        max_pages = data.get("max_pages", 50)
        max_depth = data.get("max_depth", 2)
        
        # Support queued execution
        if data.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_CRAWL, {
                    "mode": "intelligent",
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "max_pages": max_pages,
                    "max_depth": max_depth,
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Intelligent crawl task queued"}), 202
        
        emit_event(
            "intelligent_crawl",
            f"Starting intelligent crawl for '{entity_name}'",
            payload={"entity_name": entity_name, "entity_type": entity_type}
        )
        
        try:
            plan = gap_analyzer.generate_crawl_plan(entity_name, entity_type)
            
            emit_event(
                "intelligent_crawl",
                f"Crawl mode: {plan['mode']}, strategy: {plan['strategy']}",
                payload=plan
            )
            
            results = adaptive_crawler.intelligent_crawl(
                entity_name=entity_name,
                entity_type=entity_type,
                max_pages=max_pages,
                max_depth=max_depth
            )
            
            emit_event(
                "intelligent_crawl",
                "Crawl completed",
                level="info",
                payload=results
            )
            
            return jsonify({
                "plan": plan,
                "results": results
            })
        except Exception as e:
            logger.exception(f"Intelligent crawl failed for '{entity_name}'")
            emit_event("intelligent_crawl", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    @bp.route("/adaptive/status", methods=["GET"])
    @api_key_required
    def api_adaptive_crawl_status():
        """Get status and capabilities of adaptive crawling system."""
        try:
            status = adaptive_crawler.get_adaptive_strategy_summary()
            return jsonify(status)
        except Exception as e:
            logger.exception("Failed to get adaptive crawl status")
            return jsonify({"error": str(e)}), 500
    
    @bp.route("/unified", methods=["POST"])
    @api_key_required
    def api_unified_crawl():
        """Unified crawl endpoint that automatically selects between standard and intelligent crawl."""
        data = request.get_json() or {}
        
        entity_name = data.get("entity", "").strip()
        if not entity_name:
            return jsonify({"error": "entity is required"}), 400
        
        entity_type = data.get("type")
        use_intelligent = data.get("use_intelligent", False)
        
        # Support queued execution
        if data.get("queued"):
            tq = _get_task_queue()
            if tq:
                from ...services.task_queue import TaskQueueService
                task_id = tq.submit(TaskQueueService.TASK_CRAWL, {
                    "mode": "unified",
                    "entity": entity_name,
                    "type": entity_type,
                    "use_intelligent": use_intelligent,
                    "max_pages": data.get("max_pages", 50),
                    "max_depth": data.get("max_depth", 2),
                })
                return jsonify({"task_id": task_id, "status": "pending", "message": "Unified crawl task queued"}), 202
        
        if not use_intelligent:
            with store.Session() as session:
                existing = session.query(Entity).filter(
                    Entity.name.ilike(f"%{entity_name}%")
                ).first()
                if existing:
                    use_intelligent = True
                    logger.info(f"Entity '{entity_name}' found in database, using intelligent crawl")
        
        emit_event(
            "unified_crawl",
            f"Starting {'intelligent' if use_intelligent else 'standard'} crawl for '{entity_name}'",
            payload={"entity": entity_name, "mode": "intelligent" if use_intelligent else "standard"}
        )
        
        try:
            if use_intelligent:
                plan = gap_analyzer.generate_crawl_plan(entity_name, entity_type)
                
                results = adaptive_crawler.intelligent_crawl(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    max_pages=data.get("max_pages", 50),
                    max_depth=data.get("max_depth", 2)
                )
                
                emit_event(
                    "unified_crawl",
                    "Intelligent crawl completed",
                    level="info",
                    payload=results
                )
                
                return jsonify({
                    "mode": "intelligent",
                    "plan": plan,
                    "results": results
                })
            else:
                result = run_crawl_api(data)
                
                emit_event(
                    "unified_crawl",
                    "Standard crawl completed",
                    level="info"
                )
                
                return jsonify({
                    "mode": "standard",
                    "results": result
                })
                
        except Exception as e:
            logger.exception(f"Unified crawl failed for '{entity_name}'")
            emit_event("unified_crawl", f"Error: {str(e)}", level="error")
            return jsonify({"error": str(e)}), 500
    
    return bp
