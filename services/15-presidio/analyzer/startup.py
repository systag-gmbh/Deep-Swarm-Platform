#!/usr/bin/env python
"""
Startup script for Presidio Analyzer with NerGuard-0.3B recognizer.

This script:
1. Creates a custom AnalyzerEngine with NerGuard recognizer
2. Optionally keeps pattern-based recognizers for better coverage
3. Starts the Flask API server
4. Provides audit logging for PII detection
"""

import os
import sys
import logging

# Add the app directory to path
sys.path.insert(0, "/app")

from flask import Flask, request, jsonify
from flask_cors import CORS
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry

# Import custom recognizer
from ensemble_recognizer import EnsembleNerRecognizer
from anonymize import anonymize_text
from conversation import anonymize_conversation, cache_response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("presidio-startup")

# Separate audit logger
audit_logger = logging.getLogger("presidio-audit")
audit_logger.setLevel(logging.INFO)

# Configuration from environment variables
USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
PORT = int(os.getenv("PORT", "5002"))

# Audit logging configuration
AUDIT_LOGGING = os.getenv("AUDIT_LOGGING", "false").lower() == "true"
DANGER_AUDIT_LOG_PII = os.getenv("DANGER_AUDIT_LOG_PII", "false").lower() == "true"

if DANGER_AUDIT_LOG_PII:
    logger.warning("=" * 60)
    logger.warning("WARNING: DANGER_AUDIT_LOG_PII is enabled!")
    logger.warning("Actual PII values will be logged. Use only for testing!")
    logger.warning("NEVER enable this in production!")
    logger.warning("=" * 60)


def create_analyzer_engine() -> AnalyzerEngine:
    """Create and configure the AnalyzerEngine with NerGuard recognizer."""
    
    logger.info("Initializing Presidio Analyzer with NerGuard-0.3B")
    
    # Create NLP engine with blank spaCy model (tokenization only, no NER)
    # NerGuard handles all NER — no pretrained spaCy model needed.
    import spacy
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    class BlankSpacyNlpEngine(SpacyNlpEngine):
        def __init__(self):
            super().__init__()
            self.nlp = {"en": spacy.blank("en")}

    nlp_engine = BlankSpacyNlpEngine()
    logger.info("NLP engine created with spacy.blank('en') (tokenization only)")
    
    # Create recognizer registry
    registry = RecognizerRegistry()
    
    # Load default recognizers (patterns for credit cards, IBAN, etc.)
    # registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    # logger.info("Loaded predefined pattern recognizers")
    
    # Create and add ensemble recognizer
    ensemble = EnsembleNerRecognizer(
        supported_language="en",
        device="cuda" if USE_GPU else "cpu",
    )

    logger.info("Loading ensemble models (this may take a moment)...")
    ensemble.load()

    registry.add_recognizer(ensemble)
    logger.info("Ensemble recognizer registered")
    
    # Create analyzer engine - only support "en" to match registry
    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"],
    )
    
    logger.info("Analyzer engine ready")
    logger.info(f"Audit logging: {AUDIT_LOGGING}, PII logging: {DANGER_AUDIT_LOG_PII}")
    return analyzer


def log_audit(text: str, results: list, language: str) -> None:
    """
    Log audit information about PII detection.
    
    Args:
        text: Original text (only used if DANGER_AUDIT_LOG_PII is enabled)
        results: List of RecognizerResult objects
        language: Language code used for analysis
    """
    if not AUDIT_LOGGING and not DANGER_AUDIT_LOG_PII:
        return
    
    if not results:
        audit_logger.info(f"No PII detected (language={language}, text_length={len(text)})")
        return
    
    # Group results by entity type
    entity_counts = {}
    for r in results:
        entity_counts[r.entity_type] = entity_counts.get(r.entity_type, 0) + 1
    
    # Basic audit log (no PII values)
    audit_logger.info(
        f"PII detected: {len(results)} entities "
        f"(language={language}, text_length={len(text)}) - "
        f"types: {entity_counts}"
    )
    
    # Detailed log with positions
    for r in results:
        if DANGER_AUDIT_LOG_PII:
            # TESTING ONLY: Log actual PII values
            pii_value = text[r.start:r.end]
            audit_logger.info(
                f"  [{r.entity_type}] pos={r.start}:{r.end} "
                f"score={r.score:.3f} value=\"{pii_value}\""
            )
        else:
            # Production: Log only metadata
            audit_logger.info(
                f"  [{r.entity_type}] pos={r.start}:{r.end} "
                f"score={r.score:.3f} length={r.end - r.start}"
            )


# Create Flask app
app = Flask(__name__)
CORS(app)

# Initialize analyzer (done at startup)
analyzer_engine: AnalyzerEngine = None


@app.before_request
def ensure_analyzer():
    """Ensure analyzer is initialized."""
    global analyzer_engine
    if analyzer_engine is None:
        analyzer_engine = create_analyzer_engine()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Analyze text for PII entities.
    
    Request body:
    {
        "text": "string to analyze",
        "language": "en" (optional, default: "en"),
        "entities": ["PERSON", "EMAIL_ADDRESS", ...] (optional),
        "score_threshold": 0.0-1.0 (optional, default: 0.0),
        "return_decision_process": bool (optional, default: false)
    }
    """
    data = request.get_json()
    
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400
    
    text = data["text"]
    language = data.get("language", "en")
    entities = data.get("entities", None)
    score_threshold = data.get("score_threshold", 0.0)
    return_decision_process = data.get("return_decision_process", False)
    
    try:
        results = analyzer_engine.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
            return_decision_process=return_decision_process,
        )
        
        # Audit logging
        log_audit(text, results, language)
        
        # Convert results to JSON-serializable format
        response = []
        for result in results:
            item = {
                "entity_type": result.entity_type,
                "start": result.start,
                "end": result.end,
                "score": float(result.score),  # Convert float32 to Python float
            }
            if return_decision_process and result.analysis_explanation:
                item["analysis_explanation"] = {
                    "recognizer": result.analysis_explanation.recognizer,
                    "pattern_name": result.analysis_explanation.pattern_name,
                    "original_score": float(result.analysis_explanation.original_score) if result.analysis_explanation.original_score else None,
                }
            response.append(item)
        
        return jsonify(response)
    
    except Exception as e:
        logger.exception("Analysis error")
        return jsonify({"error": str(e)}), 500


@app.route("/anonymize", methods=["POST"])
def anonymize():
    """
    Anonymize text using indexed placeholders.

    Request body:
    {
        "text": "string to anonymize",
        "analyzer_results": [{"start": 0, "end": 5, "entity_type": "FIRST_NAME", "score": 0.95}, ...],
        ... (extra fields like "anonymizers" are ignored)
    }
    """
    data = request.get_json()

    if not data or "text" not in data or "analyzer_results" not in data:
        return jsonify({"error": "Missing 'text' or 'analyzer_results' in request body"}), 400

    text = data["text"]
    analyzer_results = data["analyzer_results"]

    try:
        result_text, items, entity_mapping = anonymize_text(text, analyzer_results)

        return jsonify({
            "text": result_text,
            "items": items,
            "entity_mapping": entity_mapping,
        })

    except Exception as e:
        logger.exception("Anonymization error")
        return jsonify({"error": str(e)}), 500


@app.route("/anonymize_conversation", methods=["POST"])
def anonymize_conversation_endpoint():
    """
    Anonymize a full conversation with cumulative entity mapping.

    Request body:
    {
        "session_id": "abc-123" (optional),
        "messages": [
            {"role": "user", "content": "Hi, I'm Robin Smith"},
            {"role": "assistant", "content": "Hello Robin!"},
            ...
        ]
    }
    """
    data = request.get_json()

    if not data or "messages" not in data:
        return jsonify({"error": "Missing 'messages' in request body"}), 400

    session_id = data.get("session_id")
    messages = data["messages"]

    def analyze_fn(text):
        results = analyzer_engine.analyze(text=text, language="en")
        log_audit(text, results, "en")
        return [
            {"entity_type": r.entity_type, "start": r.start, "end": r.end, "score": float(r.score)}
            for r in results
        ]

    try:
        result = anonymize_conversation(messages, session_id=session_id, analyze_fn=analyze_fn)
        return jsonify(result)
    except Exception as e:
        logger.exception("Conversation anonymization error")
        return jsonify({"error": str(e)}), 500


@app.route("/cache_response", methods=["POST"])
def cache_response_endpoint():
    """
    Cache a masked LLM response for future cache hits.

    Called by the LiteLLM post-call hook after deanonymizing.
    Stores hash(deanonymized_text) -> masked_text in the message cache.

    Request body:
    {
        "session_id": "abc-123",
        "deanonymized_text": "Hello Robin Smith!",
        "masked_text": "Hello <PERSON_1>!",
        "entity_mapping": {"<PERSON_1>": "Robin Smith"}
    }
    """
    data = request.get_json()

    if not data or "session_id" not in data or "deanonymized_text" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        cache_response(
            session_id=data["session_id"],
            deanonymized_text=data["deanonymized_text"],
            masked_text=data.get("masked_text", ""),
            entity_mapping=data.get("entity_mapping", {}),
        )
        return jsonify({"status": "cached"})
    except Exception as e:
        logger.exception("Cache response error")
        return jsonify({"error": str(e)}), 500


@app.route("/deanonymize", methods=["POST"])
def deanonymize():
    """
    Restore original values from indexed placeholders.

    Request body:
    {
        "text": "Hello <FIRST_NAME_1>, your email <EMAIL_ADDRESS_1> is confirmed.",
        "entity_mapping": {"<FIRST_NAME_1>": "Robin", "<EMAIL_ADDRESS_1>": "robin.smith@systag.com"}
    }
    """
    data = request.get_json()

    if not data or "text" not in data or "entity_mapping" not in data:
        return jsonify({"error": "Missing 'text' or 'entity_mapping' in request body"}), 400

    text = data["text"]
    entity_mapping = data["entity_mapping"]

    for placeholder, original in entity_mapping.items():
        text = text.replace(placeholder, original)

    return jsonify({"text": text})


@app.route("/supportedentities", methods=["GET"])
def supported_entities():
    """Return list of supported entity types."""
    language = request.args.get("language", "en")
    entities = analyzer_engine.get_supported_entities(language=language)
    return jsonify(entities)


@app.route("/recognizers", methods=["GET"])
def recognizers():
    """Return list of registered recognizers."""
    language = request.args.get("language", "en")
    recognizers_list = analyzer_engine.get_recognizers(language=language)
    
    response = []
    for rec in recognizers_list:
        response.append({
            "name": rec.name,
            "supported_language": rec.supported_language,
            "supported_entities": rec.supported_entities,
        })
    
    return jsonify(response)


if __name__ == "__main__":
    # Initialize analyzer at startup
    analyzer_engine = create_analyzer_engine()
    
    # Start Flask server (dev mode only)
    logger.info(f"Starting Presidio Analyzer API on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
else:
    # Running under gunicorn - initialize analyzer
    analyzer_engine = create_analyzer_engine()
