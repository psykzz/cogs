import random
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"

MAX_GUESSES = 3
MIN_LENGTH = 3
MAX_LENGTH = 8


def _load_word_set(filename: str) -> set:
    path = DATA_DIR / filename
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {w.strip().lower() for w in f if w.strip().isalpha()}


_ANSWERS: set = _load_word_set("answers.txt")
_VALID_WORDS: set = _load_word_set("valid_words.txt")


def get_random_word(length: int) -> Optional[str]:
    """Pick a random answer word of the given length."""
    pool = [w for w in _ANSWERS if len(w) == length]
    if not pool:
        pool = [w for w in _VALID_WORDS if len(w) == length]
    return random.choice(pool) if pool else None


def is_valid_guess(word: str) -> bool:
    """Return True if the word is in the valid guess dictionary."""
    return word.lower() in _VALID_WORDS or word.lower() in _ANSWERS


def compute_feedback(guess: str, word: str) -> str:
    """
    Return a feedback string of ?!- symbols for a guess against the target word.

    ! = correct letter, correct position
    ? = correct letter, wrong position
    - = letter not in word

    Handles duplicate letters correctly (Wordle-style): each letter in the
    target can only be matched once.
    """
    guess = guess.lower()
    word = word.lower()
    result = ["-"] * len(guess)
    word_remaining = list(word)

    # First pass: mark exact matches
    for i, (g, w) in enumerate(zip(guess, word)):
        if g == w:
            result[i] = "!"
            word_remaining[i] = None

    # Second pass: mark correct letters in wrong positions
    for i, g in enumerate(guess):
        if result[i] == "!":
            continue
        if g in word_remaining:
            result[i] = "?"
            word_remaining[word_remaining.index(g)] = None

    return "".join(result)


def compute_score(
    guess: str,
    word: str,
    feedback: str,
    claimed_positions: list,
    claimed_letters: list,
) -> tuple:
    """
    Calculate points earned for a guess and return new position/letter claims.

    Scoring:
    - +1 for each unique letter in the guess that appears in the target word,
      only if no player has already claimed that letter globally
    - +1 for correct position, only if (letter, pos) not already globally claimed
    - +2 bonus if the guess is the full correct word

    Returns (points_earned, new_pos_claims: list of [letter, pos], new_letter_claims: list of str).
    """
    claimed_pos_set = {(c[0], c[1]) for c in claimed_positions}
    claimed_letter_set = set(claimed_letters)
    points = 0
    new_pos_claims = []
    new_letter_claims = []
    seen_letters = set()  # deduplicate within this guess

    for i, (g, fb) in enumerate(zip(guess.lower(), feedback)):
        # Letter bonus: first player globally to find each letter wins it
        if fb in ("?", "!") and g not in seen_letters:
            seen_letters.add(g)
            if g not in claimed_letter_set:
                points += 1
                new_letter_claims.append(g)
                claimed_letter_set.add(g)

        # Position bonus: per (letter, position) globally
        if fb == "!" and (g, i) not in claimed_pos_set:
            points += 1
            new_pos_claims.append([g, i])
            claimed_pos_set.add((g, i))

    if guess.lower() == word.lower():
        points += 2

    return points, new_pos_claims, new_letter_claims
