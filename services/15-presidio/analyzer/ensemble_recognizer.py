"""
Ensemble NER Recognizer for Presidio.

Combines two models for PII detection:
- NerGuard-0.3B (DeBERTa-v3, token classification, in-process)
- GLiNER (E3-JSI/gliner-multi-pii-domains-v1, ONNX via gline-rs sidecar)
"""
import logging
import os
import re
import urllib.request
import json
from dataclasses import dataclass
from typing import List, Optional

try:
    from presidio_analyzer import EntityRecognizer, RecognizerResult, AnalysisExplanation
    from presidio_analyzer.nlp_engine import NlpArtifacts
except ImportError:
    EntityRecognizer = object  # Fallback for testing without presidio
    RecognizerResult = None
    AnalysisExplanation = None
    NlpArtifacts = None

logger = logging.getLogger("ensemble_recognizer")


def _byte_to_char(text: str, byte_offset: int) -> int:
    """Convert a UTF-8 byte offset to a Python character offset."""
    text_bytes = text.encode("utf-8")
    byte_offset = min(byte_offset, len(text_bytes))
    return len(text_bytes[:byte_offset].decode("utf-8"))


def _byte_to_char_offsets(text: str, start: int, end: int):
    """Convert UTF-8 byte offsets to Python character offsets.

    Used for models that return byte offsets (e.g. Rust-based GLiNER sidecar).
    For pure-ASCII text this is a no-op since byte == char positions.
    """
    try:
        text.encode("ascii")
        return start, end
    except UnicodeEncodeError:
        return _byte_to_char(text, start), _byte_to_char(text, end)


def _trim_entity_span(text: str, start: int, end: int):
    """Trim leading/trailing whitespace from an entity span.

    HuggingFace's aggregation_strategy="simple" can include surrounding
    whitespace in entity boundaries (e.g. " Berlin" instead of "Berlin").
    This trims it so replacements don't swallow spaces and newlines.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end

COMPATIBLE_GROUPS = [
    {"ADDRESS", "LOCATION", "ZIP_CODE"},
    {"PHONE_NUMBER", "EMAIL_ADDRESS"},
]

# More specific types listed first
SPECIFICITY_ORDER = {
    "PERSON": 0,
    "ADDRESS": 0, "ZIP_CODE": 1, "LOCATION": 2,
    "PHONE_NUMBER": 0, "EMAIL_ADDRESS": 0,
}

BOOST_FACTOR = 1.2

# NerGuard label mapping (token classification)
TOKEN_CLF_TO_PRESIDIO = {
    "GIVENNAME": "PERSON",
    "SURNAME": "PERSON",
    # TITLE is handled by post-processing title absorber (titles.py)
    "AGE": "AGE",
    "SEX": "GENDER",
    "GENDER": "GENDER",
    "IDCARDNUM": "ID_NUMBER",
    "PASSPORTNUM": "PASSPORT",
    "DRIVERLICENSENUM": "DRIVER_LICENSE",
    "SOCIALNUM": "SSN",
    "TAXNUM": "TAX_ID",
    "CREDITCARDNUMBER": "CREDIT_CARD",
    "EMAIL": "EMAIL_ADDRESS",
    "TELEPHONENUM": "PHONE_NUMBER",
    "STREET": "ADDRESS",
    "BUILDINGNUM": "ADDRESS",
    "CITY": "LOCATION",
    "ZIPCODE": "ZIP_CODE",
    "DATE": "DATE_TIME",
    "TIME": "DATE_TIME",
}

# GLiNER label mapping (span-based, from gline-rs sidecar)
GLINER_TO_PRESIDIO = {
    "person": "PERSON",
    "organization": "ORGANIZATION",
    "email": "EMAIL_ADDRESS",
    "phone number": "PHONE_NUMBER",
    "address": "ADDRESS",
    "credit card number": "CREDIT_CARD",
    "bank account number": "BANK_ACCOUNT",
    "iban": "IBAN_CODE",
    "ip address": "IP_ADDRESS",
    "username": "USERNAME",
}

# Labels to send to GLiNER for prediction
GLINER_LABELS = list(GLINER_TO_PRESIDIO.keys())

ALL_PRESIDIO_ENTITIES = list(set(
    list(TOKEN_CLF_TO_PRESIDIO.values()) +
    list(GLINER_TO_PRESIDIO.values())
))

# GLiNER sidecar URL
GLINER_URL = os.getenv("GLINER_URL", "http://gliner:5003")


@dataclass
class NormalizedResult:
    entity_type: str
    start: int
    end: int
    score: float
    source: str
    model_label: str = ""


def _overlap_ratio(a: NormalizedResult, b: NormalizedResult) -> float:
    """Compute overlap of two character spans.

    Uses intersection / min_span_length so that a span fully contained
    within a larger span always returns 1.0 (containment case).
    Falls back to intersection / union when neither span contains the other.
    """
    intersection = max(0, min(a.end, b.end) - max(a.start, b.start))
    if intersection == 0:
        return 0.0
    len_a = a.end - a.start
    len_b = b.end - b.start
    min_len = min(len_a, len_b)
    union = max(a.end, b.end) - min(a.start, b.start)
    # Use the higher of the two ratios: containment or Jaccard
    return max(intersection / min_len if min_len > 0 else 0.0,
               intersection / union if union > 0 else 0.0)


def _are_compatible(type_a: str, type_b: str) -> bool:
    """Check if two entity types are in the same compatibility group."""
    for group in COMPATIBLE_GROUPS:
        if type_a in group and type_b in group:
            return True
    return False


def _pick_specific_type(type_a: str, type_b: str) -> str:
    """Return the more specific type (lower specificity number wins)."""
    rank_a = SPECIFICITY_ORDER.get(type_a, 99)
    rank_b = SPECIFICITY_ORDER.get(type_b, 99)
    return type_a if rank_a <= rank_b else type_b


def merge_results(results: List[NormalizedResult]) -> List[NormalizedResult]:
    """Merge overlapping results from multiple models with score boosting."""
    if not results:
        return []

    # Sort by start position
    results = sorted(results, key=lambda r: (r.start, -(r.end - r.start)))

    merged: List[NormalizedResult] = []
    used = [False] * len(results)

    for i, a in enumerate(results):
        if used[i]:
            continue

        best = NormalizedResult(
            entity_type=a.entity_type,
            start=a.start,
            end=a.end,
            score=a.score,
            source=a.source,
            model_label=a.model_label,
        )
        match_count = 1

        for j in range(i + 1, len(results)):
            if used[j]:
                continue
            b = results[j]

            if _overlap_ratio(best, b) < 0.7:
                continue

            # Check relationship
            same_type = best.entity_type == b.entity_type
            compatible = _are_compatible(best.entity_type, b.entity_type)

            if same_type or compatible:
                used[j] = True
                match_count += 1
                # Keep longer span
                if (b.end - b.start) > (best.end - best.start):
                    best.start = b.start
                    best.end = b.end
                # Pick most specific type
                if compatible and not same_type:
                    best.entity_type = _pick_specific_type(best.entity_type, b.entity_type)
                # Track max score for boosting
                best.score = max(best.score, b.score)

        # Apply boost if multiple models agreed
        if match_count > 1:
            best.score = min(best.score * BOOST_FACTOR, 1.0)

        merged.append(best)

    return sorted(merged, key=lambda r: r.start)


def suppress_contained_entities(
    results: List[NormalizedResult],
) -> List[NormalizedResult]:
    """Remove entities that significantly overlap with a larger (or equal) entity of a different type.

    After merge_results combines same-type and compatible-type overlaps,
    there can still be entities of unrelated types overlapping — e.g. IBAN
    fragments mis-detected as PASSPORT/SSN, or a credit card number also
    detected as SSN at the same span.  This pass keeps only the best entity.

    Rules:
      - Same-type or compatible-type overlaps are left alone (already merged).
      - If overlap_ratio >= 0.7 and different incompatible types:
        - Different lengths: suppress the shorter entity.
        - Same length: suppress the lower-scored entity.
    """
    if len(results) <= 1:
        return results

    suppressed = [False] * len(results)

    for i, a in enumerate(results):
        if suppressed[i]:
            continue
        len_a = a.end - a.start
        for j, b in enumerate(results):
            if i == j or suppressed[j]:
                continue
            if _overlap_ratio(a, b) < 0.7:
                continue
            # Same type or compatible types already handled by merge_results
            if a.entity_type == b.entity_type or _are_compatible(a.entity_type, b.entity_type):
                continue
            len_b = b.end - b.start
            if len_a == len_b:
                # Same-length spans: suppress the lower-scored entity
                if a.score < b.score:
                    suppressed[i] = True
                    break
                elif b.score < a.score:
                    suppressed[j] = True
                # Equal scores: keep both (truly ambiguous)
            elif len_a < len_b:
                suppressed[i] = True
                break
            else:
                suppressed[j] = True

    return [r for i, r in enumerate(results) if not suppressed[i]]


# Matches our indexed placeholders like <PERSON_1>, <EMAIL_ADDRESS_2>, etc.
# Brackets are optional — NER models sometimes detect partial spans.
_PLACEHOLDER_RE = re.compile(r"^<?[A-Z][A-Z_]*_\d+>?$")

VALIDATION_RULES = {
    "EMAIL_ADDRESS": lambda text: "@" in text and len(text) >= 5,
    "PHONE_NUMBER": lambda text: len(text) >= 6,
    "CREDIT_CARD": lambda text: len(text) >= 12,
    "PERSON": lambda text: len(text) >= 2,
    "ZIP_CODE": lambda text: len(text) >= 3 and any(c.isdigit() for c in text),
    "USERNAME": lambda text: len(text) >= 4,
    "ORGANIZATION": lambda text: len(text) >= 3,
    "IP_ADDRESS": lambda text: text.count(".") >= 3 and len(text) >= 7,
    "IBAN_CODE": lambda text: len(text) >= 15,
}

MIN_SCORE = {
    "ORGANIZATION": 0.7,
}

# General score threshold — entities below this confidence are dropped.
DEFAULT_SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "0.5"))

# Entity types to never mask (comma-separated env var override).
EXCLUDED_ENTITIES = set(
    os.getenv("EXCLUDED_ENTITIES", "DATE_TIME,AGE,GENDER").split(",")
)


def validate_results(
    results: List[NormalizedResult], full_text: str
) -> List[NormalizedResult]:
    """Remove results that fail validation rules."""
    validated = []
    for r in results:
        # Skip excluded entity types
        if r.entity_type in EXCLUDED_ENTITIES:
            continue
        # Skip below general score threshold
        if r.score < DEFAULT_SCORE_THRESHOLD:
            continue
        entity_text = full_text[r.start:r.end]
        # Skip our own indexed placeholders — already-anonymized text
        # should not be re-detected as PII.
        if _PLACEHOLDER_RE.match(entity_text):
            continue
        # Check per-type minimum score (overrides general threshold)
        min_score = MIN_SCORE.get(r.entity_type)
        if min_score is not None and r.score < min_score:
            continue
        rule = VALIDATION_RULES.get(r.entity_type)
        if rule is None or rule(entity_text):
            validated.append(r)
    return validated


def absorb_titles(
    results: List[NormalizedResult], full_text: str
) -> List[NormalizedResult]:
    """Absorb known titles that precede PERSON entities into the entity span.

    When a title from the titles list appears directly before a PERSON entity
    (possibly with undetected capitalized words in between), the entity span
    is expanded backwards to include the title.  This prevents titles like
    "Dr.", "Prof.", or "Ppa." from leaking information about the masked person.
    """
    from titles import find_titles

    title_positions = find_titles(full_text)
    if not title_positions:
        return results

    for t_start, t_end in title_positions:
        # Skip titles already inside an entity span
        if any(r.start <= t_start and r.end >= t_end for r in results):
            continue

        # Scan forward past whitespace
        pos = t_end
        while pos < len(full_text) and full_text[pos] in (" ", "\t"):
            pos += 1

        # Find nearest PERSON entity after the title
        best = None
        for r in results:
            if r.entity_type != "PERSON":
                continue
            if r.start < pos:
                continue
            if r.start > t_end + 50:
                continue

            # Check gap between title and entity contains only name-like words
            gap = full_text[pos : r.start]
            if gap:
                gap_stripped = gap.strip()
                if gap_stripped:
                    gap_words = gap_stripped.split()
                    if not all(w[0].isupper() for w in gap_words):
                        continue
                    if not all(
                        c.isalpha() or c.isspace() or c == "-" for c in gap_stripped
                    ):
                        continue

            if best is None or r.start < best.start:
                best = r

        if best is not None and t_start < best.start:
            best.start = t_start

    return results


ADDRESS_TYPES = {"ADDRESS", "LOCATION", "ZIP_CODE", "ORGANIZATION"}


def merge_address_blocks(
    results: List[NormalizedResult], full_text: str
) -> List[NormalizedResult]:
    """Merge adjacent address-component entities into single ADDRESS spans.

    Entities of type ADDRESS, LOCATION, ZIP_CODE, and ORGANIZATION that are
    separated by only whitespace are collapsed into one ADDRESS entity.
    """
    if not results:
        return []

    sorted_results = sorted(results, key=lambda r: r.start)
    output: List[NormalizedResult] = []
    block: List[NormalizedResult] = []

    def _flush_block():
        if len(block) <= 1:
            output.extend(block)
        else:
            best_score = max(r.score for r in block)
            output.append(NormalizedResult(
                entity_type="ADDRESS",
                start=block[0].start,
                end=block[-1].end,
                score=best_score,
                source="merged",
            ))
        block.clear()

    for r in sorted_results:
        if r.entity_type not in ADDRESS_TYPES:
            _flush_block()
            output.append(r)
            continue

        if block:
            gap = full_text[block[-1].end:r.start]
            if gap.strip() == "":
                # Only whitespace between — extend the block
                block.append(r)
            else:
                # Non-whitespace gap — start a new block
                _flush_block()
                block.append(r)
        else:
            block.append(r)

    _flush_block()
    return sorted(output, key=lambda r: r.start)


class EnsembleNerRecognizer(EntityRecognizer):
    """
    Ensemble recognizer combining NerGuard and GLiNER.
    NerGuard runs in-process; GLiNER runs via HTTP sidecar (gline-rs).
    Results are merged with score boosting and validated.
    """

    SUPPORTED_ENTITIES = ALL_PRESIDIO_ENTITIES

    def __init__(
        self,
        supported_language: str = "en",
        supported_entities: Optional[List[str]] = None,
        device: str = "cpu",
    ):
        self.device = device
        self.nerguard_pipeline = None

        entities = supported_entities or self.SUPPORTED_ENTITIES

        super().__init__(
            supported_entities=entities,
            supported_language=supported_language,
            name="Ensemble NER Recognizer",
        )

    def load(self) -> None:
        """Load NerGuard model (GLiNER runs as external sidecar)."""
        from transformers import (
            AutoTokenizer, AutoModelForTokenClassification, pipeline,
        )

        device_arg = 0 if self.device == "cuda" else "cpu"

        # NerGuard (token classification)
        logger.info("Loading NerGuard-0.3B...")
        nerguard_tok = AutoTokenizer.from_pretrained("exdsgift/NerGuard-0.3B")
        nerguard_model = AutoModelForTokenClassification.from_pretrained("exdsgift/NerGuard-0.3B")
        self.nerguard_pipeline = pipeline(
            "token-classification", model=nerguard_model,
            tokenizer=nerguard_tok, aggregation_strategy="simple",
            device=device_arg,
        )

        logger.info("NerGuard loaded; GLiNER available via sidecar at %s", GLINER_URL)
        logger.info(
            "Filtering: score_threshold=%.2f, excluded_entities=%s",
            DEFAULT_SCORE_THRESHOLD, EXCLUDED_ENTITIES,
        )

    def _run_token_clf(self, pipeline_obj, text, mapping, source):
        """Run a HF token-classification pipeline and normalize.

        HuggingFace pipelines return character offsets — use them as-is.
        """
        try:
            raw = pipeline_obj(text)
        except Exception as e:
            logger.error(f"{source} error: {e}")
            return []

        results = []
        for ent in raw:
            label = ent["entity_group"]
            presidio_type = mapping.get(label)
            if presidio_type is None:
                logger.warning(
                    f"{source}: unmapped label '{label}' for "
                    f"'{text[ent['start']:ent['end']]}' "
                    f"(score={ent['score']:.3f})"
                )
                continue
            start, end = _trim_entity_span(text, ent["start"], ent["end"])
            results.append(NormalizedResult(
                entity_type=presidio_type,
                start=start,
                end=end,
                score=float(ent["score"]),
                source=source,
                model_label=label,
            ))
        return results

    def _run_gliner(self, text):
        """Call GLiNER sidecar via HTTP and normalize results."""
        try:
            payload = json.dumps({
                "text": text,
                "labels": GLINER_LABELS,
            }).encode()
            req = urllib.request.Request(
                f"{GLINER_URL}/predict",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                entities = json.loads(resp.read())
        except Exception as e:
            logger.error(f"GLiNER sidecar error: {e}")
            return []

        results = []
        for ent in entities:
            presidio_type = GLINER_TO_PRESIDIO.get(ent["label"])
            if presidio_type is None:
                logger.warning(
                    f"gliner: unmapped label '{ent['label']}' for "
                    f"'{ent['text']}' (score={ent['score']:.3f})"
                )
                continue
            # GLiNER Rust sidecar returns UTF-8 byte offsets — convert
            start, end = _byte_to_char_offsets(
                text, ent["start"], ent["end"],
            )
            start, end = _trim_entity_span(text, start, end)
            results.append(NormalizedResult(
                entity_type=presidio_type,
                start=start,
                end=end,
                score=float(ent["score"]),
                source="gliner",
                model_label=ent["label"],
            ))
        return results

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        if self.nerguard_pipeline is None:
            self.load()

        # 1. Run both models
        all_results = []
        all_results += self._run_token_clf(
            self.nerguard_pipeline, text, TOKEN_CLF_TO_PRESIDIO, "nerguard"
        )
        all_results += self._run_gliner(text)

        # Log raw detections from each model
        if all_results:
            logger.info("Raw detections (%d entities):", len(all_results))
            for r in sorted(all_results, key=lambda r: r.start):
                label_info = f", label={r.model_label}" if r.model_label else ""
                logger.info(
                    "  [raw] %s: %s pos=%d:%d score=%.3f%s",
                    r.source, r.entity_type, r.start, r.end, r.score, label_info,
                )

        # 2. Merge overlapping results
        merged = merge_results(all_results)

        # 2b. Suppress cross-type containment (e.g. IBAN fragments → PASSPORT/SSN)
        merged = suppress_contained_entities(merged)

        # 3. Validate
        validated = validate_results(merged, text)

        # 4. Merge adjacent address components into single blocks
        validated = merge_address_blocks(validated, text)

        # 5. Absorb titles preceding PERSON entities
        validated = absorb_titles(validated, text)

        # Log final validated results
        if validated:
            logger.info("Final results (%d entities):", len(validated))
            for r in validated:
                label_info = f", label={r.model_label}" if r.model_label else ""
                logger.info(
                    "  [final] %s pos=%d:%d score=%.3f (source=%s%s)",
                    r.entity_type, r.start, r.end, r.score, r.source, label_info,
                )

        # 6. Convert to Presidio RecognizerResult
        presidio_results = []
        for r in validated:
            if r.entity_type not in entities:
                continue
            explanation = AnalysisExplanation(
                recognizer=self.name,
                original_score=r.score,
                pattern_name=f"ensemble:{r.source}",
                pattern=None,
                validation_result=None,
            )
            presidio_results.append(RecognizerResult(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                score=r.score,
                analysis_explanation=explanation,
                recognition_metadata={
                    RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                    RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                },
            ))

        return presidio_results
