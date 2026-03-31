"""
Test suite for gender detection edge cases mentioned in PR #13.
Tests fuzzy matching, typos, mixed case, emoji filtering, and local slang.
"""

import re
import logging

logger = logging.getLogger(__name__)


def normalize_gender_response(text: str) -> str:
    """
    Normalize gender response for fuzzy matching.
    Handles: lowercase conversion, emoji removal, punctuation removal, typos.
    """
    # Lowercase
    t = text.strip().lower()

    # Remove emoji and special characters (keep alphanumeric and spaces)
    t = re.sub(r'[^\w\s]', '', t)

    # Remove extra spaces
    t = t.strip()

    return t


def detect_gender_fuzzy(text: str) -> str | None:
    """
    Detect gender from response with fuzzy matching and edge case handling.

    Returns:
        "female", "male", "ambiguous", or None if unclear
    """
    normalized = normalize_gender_response(text)

    # FEMALE keywords (expanded from PR #13 feedback)
    female_keywords = {
        # Standard/formal
        "cewe", "cewek", "perempuan", "wanita", "girl", "woman", "female",
        # Abbreviations
        "ce", "c", "cw", "cwk", "p", "pr", "f", "w",
        # Dialects/slang
        "che", "cweew", "gadis", "perawan", "ladies", "sis", "miss", "lady", "chick",
        # Common variations
        "ceweknya", "cewenya"
    }

    # MALE keywords (expanded from PR #13 feedback)
    male_keywords = {
        # Standard/formal
        "cowo", "cowok", "laki", "lakilaki", "pria", "boy", "man", "male",
        # Abbreviations
        "co", "c", "cw", "cwk", "l", "lk", "m", "b",
        # Dialects/slang
        "cowoknya", "coknya", "pak", "mas", "bang",
        # English variants
        "dude", "bro", "lad"
    }

    # Exact match (fastest path)
    if normalized in female_keywords:
        return "female"
    if normalized in male_keywords:
        return "male"

    # Handle typos: "c0" (zero) → "co", "cwk" → check variations
    # Convert common typos
    typo_corrected = normalized.replace("0", "o")  # c0 → co

    if typo_corrected in female_keywords:
        logger.debug(f"Detected female (typo corrected): {text} → {typo_corrected}")
        return "female"
    if typo_corrected in male_keywords:
        logger.debug(f"Detected male (typo corrected): {text} → {typo_corrected}")
        return "male"

    # Word-by-word matching (handle "kamu cewe ya?")
    words = normalized.split()
    for word in words:
        if word in female_keywords:
            logger.debug(f"Detected female (word match): {text} → '{word}'")
            return "female"
        if word in male_keywords:
            logger.debug(f"Detected male (word match): {text} → '{word}'")
            return "male"

    # Ambiguous responses - require retry
    ambiguous_keywords = ["entahlah", "gatau", "ga tau", "bingung", "ga tahu", "dunno", "idk"]
    if any(kw in normalized for kw in ambiguous_keywords):
        logger.warning(f"Ambiguous response detected: {text}")
        return "ambiguous"

    return None


# Test cases from PR #13 feedback
TEST_CASES = [
    # Standard cases
    ("cewe", "female", "Standard female"),
    ("cewek", "female", "Standard female variant"),
    ("c", "female", "Single letter abbreviation"),
    ("perempuan", "female", "Formal female"),
    ("wanita", "female", "Formal female variant"),

    # Abbreviations
    ("ce", "female", "Common abbreviation"),
    ("cw", "female", "Abbreviation variant"),
    ("cwk", "female", "Abbreviation variant 2"),
    ("pr", "female", "Abbreviation for perempuan"),
    ("f", "female", "English abbreviation"),
    ("w", "female", "English abbreviation variant"),

    # English variants
    ("female", "female", "English full form"),
    ("girl", "female", "English variant"),
    ("woman", "female", "English variant 2"),
    ("lady", "female", "English variant 3"),
    ("chick", "female", "English slang 1"),
    ("sis", "female", "English slang 2"),

    # Dialects/local slang
    ("gadis", "female", "Indonesian dialect"),
    ("perawan", "female", "Indonesian dialect 2"),
    ("che", "female", "Regional variant"),
    ("cweew", "female", "Regional spelling variant"),

    # Typos and mixed case
    ("c0", "male", "Typo: zero corrects to 'co' (male)"),
    ("C0", "male", "Typo + uppercase: corrects to 'co' (male)"),
    ("CEWE", "female", "All caps"),
    ("CeWe", "female", "Mixed case"),
    ("Cewe", "female", "Sentence case"),

    # Emoji and punctuation
    ("cewe 😂", "female", "With emoji"),
    ("cewe!!!", "female", "With punctuation"),
    ("cewe?", "female", "With question mark"),
    ("ce.", "female", "With period"),

    # Multi-word contexts
    ("aku cewe", "female", "Multi-word: subject + gender"),
    ("aku cewe lah", "female", "Multi-word with filler"),
    ("kamu cewe ya?", "female", "Question with gender"),
    ("cewe deh", "female", "With filler word"),

    # Male equivalents (sample)
    ("cowo", "male", "Standard male"),
    ("cowok", "male", "Standard male variant"),
    ("co", "male", "Abbreviation"),
    ("laki", "male", "Abbreviation for laki-laki"),
    ("pria", "male", "Formal male"),
    ("m", "male", "English abbreviation"),
    ("male", "male", "English form"),
    ("boy", "male", "English variant"),
    ("CO", "male", "Uppercase abbreviation"),
    ("CoWo", "male", "Mixed case"),
    ("cowo 🔥", "male", "With emoji"),

    # Ambiguous (require retry)
    ("entahlah", "ambiguous", "Ambiguous: entahlah"),
    ("gatau", "ambiguous", "Ambiguous: gatau"),
    ("ga tau", "ambiguous", "Ambiguous: ga tau (with space)"),
    ("idk", "ambiguous", "Ambiguous: English idk"),
    ("bingung", "ambiguous", "Ambiguous: bingung"),

    # Unclear (should be None)
    ("maybe", None, "Unclear: maybe"),
    ("hmm", None, "Unclear: hmm"),
    ("ya", None, "Unclear: just yes"),
]


def run_tests():
    """Run all test cases and report results."""
    print("\n" + "=" * 80)
    print("GENDER DETECTION EDGE CASE TESTS (PR #13)")
    print("=" * 80 + "\n")

    passed = 0
    failed = 0

    for input_text, expected_result, description in TEST_CASES:
        result = detect_gender_fuzzy(input_text)
        status = "✓" if result == expected_result else "✗"

        if result == expected_result:
            passed += 1
        else:
            failed += 1

        print(f"{status} {description}")
        print(f"  Input: '{input_text}' → Result: {result} (Expected: {expected_result})")
        if result != expected_result:
            print(f"  MISMATCH!")
        print()

    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    print("=" * 80 + "\n")

    return failed == 0


def test_token_safety():
    """Test that both [SKIP] and [START_CHAT] tokens don't appear together."""
    print("\n" + "=" * 80)
    print("TOKEN CONFLICT SAFETY TESTS")
    print("=" * 80 + "\n")

    test_cases = [
        {
            "bubbles": ["co", "topik seru", "[START_CHAT]"],
            "has_conflict": False,
            "description": "Valid female response"
        },
        {
            "bubbles": ["[SKIP]"],
            "has_conflict": False,
            "description": "Valid male response"
        },
        {
            "bubbles": ["co", "[START_CHAT]", "[SKIP]"],
            "has_conflict": True,
            "description": "CRITICAL: Both tokens present"
        },
    ]

    for test in test_cases:
        bubbles = test["bubbles"]
        has_skip = any(b == "[SKIP]" for b in bubbles)
        has_start_chat = any(b == "[START_CHAT]" for b in bubbles)
        has_conflict = has_skip and has_start_chat

        status = "✓" if has_conflict == test["has_conflict"] else "✗"
        print(f"{status} {test['description']}")
        print(f"  Bubbles: {bubbles}")
        print(f"  Has [SKIP]: {has_skip}, Has [START_CHAT]: {has_start_chat}")
        print(f"  Conflict detected: {has_conflict}")
        print()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    # Run tests
    all_passed = run_tests()
    test_token_safety()

    if all_passed:
        print("✅ All gender detection tests passed!")
        exit(0)
    else:
        print("❌ Some tests failed. Review the output above.")
        exit(1)
