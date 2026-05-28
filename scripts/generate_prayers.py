#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

# Reconfigure console encoding to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Setup path to import from parent directory
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.bible_service import BibleService, DEFAULT_TRANSLATION_FOR_LANG
from services.prayer_service import PRAYERS_FILE

# Set up logging
logger = logging.getLogger("prayer_generator")
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# File handler with UTF-8 encoding
log_file = Path(__file__).parent.parent / "data" / "generation.log"
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setFormatter(formatter)
logger.addHandler(fh)

# Stream handler with sys.stdout
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
logger.addHandler(sh)

# Initialize Gemini Client
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.error("GEMINI_API_KEY not found in environment or .env file!")
    sys.exit(1)

client = genai.Client(api_key=api_key)

# State file path
STATE_FILE = Path(__file__).parent.parent / "data" / "prayers_generation_state.json"

THEMES = [
    {"id": "gratitude_praise", "name_ru": "Благодарность и хвала", "count": 30},
    {"id": "faith_trust", "name_ru": "Вера и доверие", "count": 30},
    {"id": "peace_rest", "name_ru": "Мир и покой", "count": 30},
    {"id": "hope_confidence", "name_ru": "Надежда и упование", "count": 30},
    {"id": "love_mercy", "name_ru": "Любовь и милосердие", "count": 30},
    {"id": "strength_trials", "name_ru": "Сила в испытаниях", "count": 30},
    {"id": "guidance_wisdom", "name_ru": "Водительство и мудрость", "count": 30},
    {"id": "family_relationships", "name_ru": "Семья и близкие", "count": 30},
    {"id": "humility_repentance", "name_ru": "Смирение и покаяние", "count": 30},
    {"id": "joy_comfort", "name_ru": "Радость и утешение", "count": 30},
    {"id": "service_witness", "name_ru": "Служение и благовестие", "count": 30},
    {"id": "spiritual_growth", "name_ru": "Духовный рост и святость", "count": 35},
]

class LocaleString(BaseModel):
    ru: str = Field(description="Russian text, warm and sincere personal prayer (~150 chars), or short title")
    en: str = Field(description="English text, warm and sincere personal prayer (~150 chars), or short title")
    es: str = Field(description="Spanish text, warm and sincere personal prayer (~150 chars), or short title")
    uk: str = Field(description="Ukrainian text, warm and sincere personal prayer (~150 chars), or short title")

class PrayerItem(BaseModel):
    id: str = Field(description="Slug identifier, e.g., gratitude_praise_01")
    ref: str = Field(description="Bible verse reference in format 'abbrev:chapter:verse' (e.g. 'ps:23:1') using standard books.yaml abbreviations")
    title: LocaleString
    text: LocaleString

class PrayerBatchResponse(BaseModel):
    prayers: list[PrayerItem]


def get_valid_abbrevs_string() -> str:
    """Formats the list of valid abbreviations from BibleService."""
    ot_books = []
    nt_books = []
    for abbrev, meta in BibleService._books_meta.items():
        testament = meta.get("testament")
        info = f"'{abbrev}' (for {meta.get('en')}/{meta.get('ru')})"
        if testament == "ot":
            ot_books.append(info)
        elif testament == "nt":
            nt_books.append(info)
    
    return f"""VALID BIBLE BOOK ABBREVIATIONS (USE ONLY THESE KEYS AS THE BOOK PART IN 'abbrev:chapter:verse'):
Old Testament: {", ".join(ot_books)}

New Testament: {", ".join(nt_books)}
"""


def validate_ref(ref_str: str) -> bool:
    """Validates if the bible verse exists in our local translations."""
    try:
        if not ref_str or ":" not in ref_str:
            return False
        parts = ref_str.strip().lower().split(":")
        if len(parts) != 3:
            return False
        abbrev, chapter_s, verse_s = parts
        chapter = int(chapter_s)
        verse = int(verse_s)
        
        # Verify book abbreviation is known in metadata
        if abbrev not in BibleService._books_meta:
            return False
            
        # Verify chapter and verse exist in our main translations
        for lang, trans in DEFAULT_TRANSLATION_FOR_LANG.items():
            verse_text = BibleService.get_verse(abbrev, chapter, verse, trans)
            if not verse_text:
                return False
        return True
    except Exception as e:
        logger.debug(f"Validation error for '{ref_str}': {e}")
        return False


def load_state() -> dict:
    """Loads the progress state from JSON file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
    return {"completed_prayers": []}


def save_state(state: dict):
    """Saves the progress state to JSON file."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving state file: {e}")


def generate_batch(theme_id: str, theme_name: str, start_idx: int, count: int, invalid_refs: list[str] = None) -> list[dict]:
    """Calls Gemini to generate a batch of prayers."""
    abbrev_list_str = get_valid_abbrevs_string()
    
    invalid_prompt = ""
    if invalid_refs:
        invalid_prompt = f"\nIMPORTANT: The following bible references were previously generated but are INVALID or do not exist in our Bible databases: {invalid_refs}. DO NOT USE THEM. Provide different, fully valid, well-known bible verse references."

    prompt = f"""You are a theologian, pastoral counselor, and creative writer.
We need to generate {count} daily prayers for the theme: "{theme_name}" (Theme ID: {theme_id}).
The prayers are numbered from {start_idx} to {start_idx + count - 1}.
Generate a JSON object matching the requested schema.

{abbrev_list_str}

CRITICAL RULES FOR `ref`:
1. The `ref` field must contain exactly one single verse reference in the format `abbrev:chapter:verse` (e.g., `ps:23:1`, `mt:6:33`, `ph:4:6`).
2. You MUST use one of the abbreviation keys from the list above. DO NOT use common abbreviations like 'col', '1th', '1cor', 'hebr', 'deut' - you MUST use the exact keys: 'cl' for Colossians, '1ts' for 1 Thessalonians, '1co' for 1 Corinthians, 'hb' for Hebrews, 'dt' for Deuteronomy, 'eph' for Ephesians, 'lm' for Lamentations.
3. NEVER use verse ranges or dashes (e.g. '3:22-23' is INVALID; you must use a single verse like '3:22').

Guidelines for Prayers:
1. Each prayer must have a stable unique id (e.g. "{theme_id}_{start_idx:02d}", "{theme_id}_{(start_idx + 1):02d}", etc.).
2. The `title` should be a short, beautiful title for the prayer (1-4 words) in Russian, English, Spanish, and Ukrainian.
3. The `text` should be a sincere, warm, deep personal prayer in the first-person singular (starting with "Lord...", "God...", "Father..." or their equivalents). It should be about 120 to 180 characters long in each language (depending on language) and directly stand on the promise of the scripture reference.
4. All 4 languages (ru, en, es, uk) must be high-quality, natural-sounding translations of each other. Avoid archaic, artificial, or church-slavonic words. Use warm modern language.
{invalid_prompt}

Generate a list of {count} prayers now."""

    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PrayerBatchResponse,
                temperature=0.75,
            ),
        )
        
        # Parse output
        data = json.loads(response.text)
        return data.get("prayers", [])
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return []


def generate_batch_with_retry(theme_id: str, theme_name: str, start_idx: int, count: int, invalid_refs: list[str] = None) -> list[dict]:
    """Generates prayers with safe exponential backoff and longer sleeps on quota limits."""
    backoff = 8.0
    
    for attempt in range(8):
        logger.info(f"Attempting generation with model gemini-3.1-flash-lite (Attempt {attempt+1}/8)...")
        
        prayers = generate_batch(theme_id, theme_name, start_idx, count, invalid_refs)
        if prayers and len(prayers) == count:
            return prayers
            
        # Sleep for a longer period (130s) to guarantee the sliding window clears
        sleep_time = backoff
        if attempt >= 1:
            logger.warning("Generation failed or rate-limited. Taking a guaranteed 130-second sleep to clear the sliding window limit...")
            sleep_time = 130.0
            
        logger.warning(f"Generation failed on attempt {attempt+1}. Sleeping for {sleep_time} seconds...")
        time.sleep(sleep_time)
        backoff *= 2.0
        
    return []


def main():
    logger.info("Starting 365 daily prayers generation...")
    
    # Initialize BibleService
    BibleService.load()
    
    state = load_state()
    completed = state.get("completed_prayers", [])
    completed_ids = {p["id"] for p in completed}
    
    logger.info(f"Loaded progress state. Already completed: {len(completed_ids)} / 365 prayers.")
    
    # Batch size of 20 fits within unverified daily quotas (needs fewer requests)
    batch_size = 20
    
    for theme in THEMES:
        theme_id = theme["id"]
        theme_name = theme["name_ru"]
        theme_target = theme["count"]
        
        logger.info(f"Processing Theme: {theme_id} ({theme_name}), Target: {theme_target} prayers.")
        
        # Generate prayers for this theme
        idx = 1
        while idx <= theme_target:
            prayer_id = f"{theme_id}_{idx:02d}"
            
            # Skip if already completed
            if prayer_id in completed_ids:
                idx += 1
                continue
            
            # Determine current batch size
            current_batch_size = min(batch_size, theme_target - idx + 1)
            batch_ids = [f"{theme_id}_{i:02d}" for i in range(idx, idx + current_batch_size)]
            
            # Filter out any that might already exist (defensive check)
            batch_ids_to_gen = [bid for bid in batch_ids if bid not in completed_ids]
            if not batch_ids_to_gen:
                idx += current_batch_size
                continue
                
            logger.info(f"Generating batch of {len(batch_ids_to_gen)} prayers starting at {prayer_id}...")
            
            invalid_refs = []
            success = False
            retries = 0
            
            while not success and retries < 4:
                prayers = generate_batch_with_retry(theme_id, theme_name, idx, len(batch_ids_to_gen), invalid_refs)
                if not prayers:
                    logger.warning(f"Batch generation failed completely. Retrying batch after 130s sleep... (Retries: {retries + 1}/4)")
                    time.sleep(130)
                    retries += 1
                    continue
                
                # Validate references
                batch_valid = True
                temp_invalid = []
                for p in prayers:
                    ref = p.get("ref", "")
                    if not validate_ref(ref):
                        logger.warning(f"Invalid reference generated: '{ref}' in prayer '{p.get('id')}'")
                        temp_invalid.append(ref)
                        batch_valid = False
                
                if batch_valid:
                    # All references in this batch are valid! Save them to completed list
                    for p in prayers:
                        completed.append(p)
                        completed_ids.add(p["id"])
                    
                    state["completed_prayers"] = completed
                    save_state(state)
                    logger.info(f"Batch from {prayer_id} successfully generated and validated.")
                    success = True
                    idx += len(batch_ids_to_gen)
                else:
                    invalid_refs.extend(temp_invalid)
                    # Deduplicate
                    invalid_refs = list(set(invalid_refs))
                    logger.warning(f"Batch contains invalid references. Regenerating with invalid refs feedback... (Attempt {retries + 1}/4)")
                    retries += 1
                    time.sleep(5)
            
            if not success:
                logger.error(f"Failed to generate valid batch starting at {prayer_id} after multiple retries. Exiting.")
                sys.exit(1)
                
            # IMPORTANT: Sleep for 25.0 seconds after a successful batch to stay safely under any sliding API rate limit!
            logger.info("Batch completed. Sleeping for 25.0s to respect API rate limits...")
            time.sleep(25.0)

    # All prayers generated successfully!
    logger.info("All 365 prayers successfully generated and validated!")
    
    # Sort prayers by theme and index to maintain perfect order
    theme_order_map = {t["id"]: idx for idx, t in enumerate(THEMES)}
    
    def sort_key(p):
        p_id = p["id"]
        parts = p_id.rsplit("_", 1)
        theme_part = parts[0]
        try:
            index_part = int(parts[1])
        except (IndexError, ValueError):
            index_part = 999
        return (theme_order_map.get(theme_part, 999), index_part)
        
    sorted_prayers = sorted(completed, key=sort_key)
    
    # Write to final YAML file
    logger.info(f"Writing {len(sorted_prayers)} prayers to {PRAYERS_FILE}...")
    
    try:
        with open(PRAYERS_FILE, "w", encoding="utf-8") as f:
            f.write("# Пул молитв на каждый день (365 дней).\n")
            f.write("# Поля:\n")
            f.write("#   id     — стабильный slug темы и номера дня\n")
            f.write("#   title  — короткий заголовок молитвы на 4 языках\n")
            f.write("#   text   — собственно текст молитвы на 4 языках (около 150 символов)\n")
            f.write("#   ref    — ссылка на стих «abbrev:chapter:verse»\n\n")
            
            yaml.dump(sorted_prayers, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
        logger.info("YAML file written successfully!")
        
        # Verify loading using yaml
        with open(PRAYERS_FILE, "r", encoding="utf-8") as f:
            test_load = yaml.safe_load(f)
        logger.info(f"Verification: Successfully loaded {len(test_load)} prayers from YAML file.")
        
        # Delete temporary state file
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            logger.info("Temporary state file removed.")
            
    except Exception as e:
        logger.error(f"Error writing or verifying final YAML file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
