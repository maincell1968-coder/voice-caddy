import sys
from pathlib import Path

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VOICE_CADDY_DIR))

from golf_rules_module import load_rules_data, render_rules_academy

def test_rules_and_quizzes_integrity():
    data = load_rules_data()
    rules = data.get("rules", [])
    quizzes = data.get("quizzes", [])

    print(f"Loaded {len(rules)} rules and {len(quizzes)} quizzes.")
    assert len(rules) >= 8, f"Expected at least 8 rules, got {len(rules)}"
    assert len(quizzes) >= 10, f"Expected at least 10 quizzes, got {len(quizzes)}"

    for rule in rules:
        assert "id" in rule
        assert "rule_number" in rule
        assert "title" in rule
        assert "category" in rule
        assert "official_principle" in rule
        assert "relief_options" in rule
        assert len(rule["relief_options"]) > 0

    for q in quizzes:
        assert "id" in q
        assert "scenario" in q
        assert "options" in q
        assert "correct_index" in q
        assert "explanation" in q
        assert 0 <= q["correct_index"] < len(q["options"]), f"Invalid correct_index for quiz {q['id']}"

    print("[OK] All integrity tests passed successfully!")

if __name__ == "__main__":
    test_rules_and_quizzes_integrity()
