# Issue #14 Fix: Gender Detection Ambiguity with "co"

## Problem Description

**Bug**: When a stranger responds with "co" (abbreviation for "cowok" = male), the system incorrectly detects them as female and transitions to CHATTING mode instead of skipping to the next match.

**Root Cause**: "co" appears in TWO conflicting places:
1. As a **male gender keyword** (stranger's response: "co" = cowok/male)
2. As the **bot's female confirmation** message (old workflow output "co")

When the bot outputs "co", and later receives more messages, the AI model might confuse the bot's own "co" output with a male keyword from the stranger, creating ambiguity in gender detection.

**Secondary Issue**: The rigid 3-phase flow (greeting → gender question → detection) doesn't handle cases where gender is revealed unprompted.

---

## Solution

### 1. **Eliminate Ambiguous "co" in Bot Output** (`persona.txt`)

**Change line 18:**
```
OLD: - Ditanya gender ("kmu?", "hbu?", "co ce?"): jawab "co" atau "cowok"
NEW: - Ditanya gender ("kmu?", "hbu?", "co ce?"): jawab "cowok" (JANGAN pakai "co" — terlalu mirip jawaban stranger, bisa bikin ambiguitas)
```

**Impact**:
- Bot now ALWAYS outputs full "cowok" when confirming male gender
- Removes the identical overlap between bot output ("co") and stranger input ("co")
- Even though "cowok" is still a male keyword, it's distinguishable from the abbreviation "co"

### 2. **Add Flexible Gender Detection Logic** (`workflow.txt`)

**Key Changes**:
1. **Removed rigid phase structure**: No longer enforces strict "greeting → ask gender → detect" sequence
2. **Added context-aware detection**:
   - If stranger reveals gender in FIRST response after greeting (e.g., "hii ce nih"), skip gender question and detect immediately
   - If gender keyword appears anywhere, detect and respond appropriately
3. **Added ambiguity handling**:
   - If response is ambiguous ("entahlah", "ga tau"), retry with natural gender question
   - Fallback: assume FEMALE for better retention
4. **Clarified "co" validity**:
   - "co" is ONLY valid as male when it's the stranger's response
   - Bot's "cowok" output will NOT trigger male detection on next turn (different word)

**Example Flow Change**:
```
BEFORE (Rigid):
Bot: hii
Stranger: hii cewe
Bot: (asks gender anyway - "co ce?")
Stranger: cewe
Bot: (detects gender)

AFTER (Flexible):
Bot: hii
Stranger: hii cewe
Bot: (detects female immediately - skips gender question)
```

---

## Files Modified

### `persona.txt`
- **Line 18**: Changed gender confirmation from "co" atau "cowok" → "cowok" (only)
- Added note explaining why "co" abbreviation is avoided

### `workflow.txt`
- Complete rewrite of gender detection workflow
- Replaced "co" with "cowok" in all bot confirmation outputs
- Added flexible detection logic (context-aware, not phase-based)
- Added ambiguity handling with retry mechanism
- Clarified when "co" is valid (stranger input only, not bot output)
- Added edge case handling: typos, emoji, mixed case, punctuation
- Added early gender disclosure handling

---

## Testing

**Test Suite**: `test_issue14_fix.py` (19 tests, all passing)

### Test 1: Core Bug Fix — "co" Detection
- ✓ "co" correctly detected as MALE
- ✓ "CO" (uppercase) detected as MALE
- ✓ "co?" (with punctuation) detected as MALE
- ✓ "co lah" (with filler) detected as MALE
- ✓ "yaa co" (in context) detected as MALE

### Test 2: Bot Output — Ambiguity Prevention
- ✓ Bot uses "cowok" (full form) — distinguishable from "co"
- ✓ Bot avoids "co" (abbreviation) — would confuse with stranger input

### Test 3: Flexible Detection
- ✓ Female upfront: "hii cewe" → detected immediately (skips gender question)
- ✓ Female upfront: "hi aku ce" → detected immediately
- ✓ Female upfront: "halo perempuan deh" → detected immediately
- ✓ Male upfront: "hii cowo" → detected immediately
- ✓ Male upfront: "hi co" → detected immediately
- ✓ Male upfront: "halo pria" → detected immediately
- ✓ No gender disclosed: "hii" → waits for gender answer
- ✓ No gender disclosed: "hi apa kabar" → waits for gender answer

### Test 4: Edge Cases
- ✓ Typo: "c0" (zero) → normalized to "co" (male)
- ✓ Caps: "COWOK" → normalized to "cowok" (male)
- ✓ Emoji: "cewe 😂" → normalized to "cewe" (female)
- ✓ Punctuation: "co??" → normalized to "co" (male)

---

## Verification Checklist

- [x] "co" is no longer used in bot output (changed to "cowok")
- [x] Gender detection works for both rigid and flexible scenarios
- [x] Early gender disclosure is handled (skips gender question)
- [x] Ambiguity handling in place (retry + fallback)
- [x] "co" is still valid as male keyword from stranger (correct detection)
- [x] "cowok" is recognized as full form (distinguishable from "co")
- [x] All 19 tests passing
- [x] No changes to `main.py` or `gemini_client.py` (as specified in issue)

---

## Impact

**Before Fix**:
- Stranger replies "co" (male) → System might misdetect as female
- Rigid flow requires gender question even if already answered
- "co" ambiguity causes unpredictable behavior

**After Fix**:
- Stranger replies "co" (male) → Correctly detected as MALE → [SKIP] sent
- Natural flow: detects gender whenever revealed, no forced questions
- Clear distinction: bot uses "cowok", stranger uses "co"
- Flexible and context-aware: handles early gender disclosure

---

## Notes

- The fix maintains backward compatibility with existing gender keyword detection
- The change from "co" → "cowok" is minimal but eliminates the core ambiguity
- Flexible detection improves natural flow and conversation quality
- All enhancements are documented in `workflow.txt` for future maintenance
