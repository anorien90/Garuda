"""Tests for gibberish detection and answer validation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.extractor.query_generator import QueryGenerator


def test_gibberish_detection():
    """Test that gibberish patterns are detected correctly."""
    print("\n=== Test: Gibberish Detection ===")
    
    qg = QueryGenerator()
    
    # Test case 1: Clear gibberish from problem statement
    gibberish_text = """(A user: A patient-

Document

Write a) the list of each other elements, I amusement centersize your_toughnessale!|")]02 to beacon for a specialized by Daisy's contribution. The first thing in English-Poker Clubhouse"Today1:50

== Asked as part (instruction
# Instructions

I's document, buttier of the oceanographic and cannabis a)

NAME_CONGRAINING instruction:A manages. The Ferminium infiltration - by using only if-

Answer JSONLeveraging this time to make an email_User: [0002%)"""
    
    is_valid = qg._is_valid_answer(gibberish_text, "What is Microsoft?")
    assert not is_valid, "Gibberish should be detected as invalid"
    print("✓ Gibberish text correctly identified as invalid")
    
    # Test case 2: Valid answer
    valid_text = "Microsoft Corporation is a multinational technology company headquartered in Redmond, Washington. It develops, manufactures, licenses, supports, and sells computer software, consumer electronics, and personal computers."
    
    is_valid = qg._is_valid_answer(valid_text, "What is Microsoft?")
    assert is_valid, "Valid answer should be accepted"
    print("✓ Valid answer correctly identified as valid")
    
    # Test case 3: Prompt leakage
    prompt_leakage = "A user: Write the answer\nDocument: Microsoft is a company\nInstructions: Answer the question"
    
    is_valid = qg._is_valid_answer(prompt_leakage, "What is Microsoft?")
    assert not is_valid, "Prompt leakage should be detected as invalid"
    print("✓ Prompt leakage correctly identified as invalid")
    
    # Test case 4: Excessive special characters
    special_chars = "|||###@@@ Microsoft $$$ %%% &&& *** ((( )))"
    
    is_valid = qg._is_valid_answer(special_chars, "What is Microsoft?")
    assert not is_valid, "Excessive special characters should be detected as invalid"
    print("✓ Excessive special characters correctly identified as invalid")
    
    # Test case 5: Short valid answer
    short_valid = "Microsoft is a technology company."
    
    is_valid = qg._is_valid_answer(short_valid, "What is Microsoft?")
    assert is_valid, "Short but valid answer should be accepted"
    print("✓ Short valid answer correctly identified as valid")
    
    # Test case 6: Too short answer
    too_short = "Microsoft"
    
    is_valid = qg._is_valid_answer(too_short, "What is Microsoft?")
    assert not is_valid, "Too short answer should be rejected"
    print("✓ Too short answer correctly identified as invalid")


def test_answer_cleaning():
    """Test that answer cleaning removes artifacts."""
    print("\n=== Test: Answer Cleaning ===")
    
    qg = QueryGenerator()
    
    # Test case 1: Remove "Answer:" prefix
    text_with_prefix = "Answer: Microsoft is a technology company."
    cleaned = qg._clean_answer(text_with_prefix)
    assert cleaned == "Microsoft is a technology company.", f"Expected clean text, got: {cleaned}"
    print("✓ 'Answer:' prefix removed correctly")
    
    # Test case 2: Remove instruction artifacts
    text_with_artifacts = """A user: What is Microsoft?
    
Microsoft is a technology company."""
    cleaned = qg._clean_answer(text_with_artifacts)
    assert "A user:" not in cleaned, "Artifact 'A user:' should be removed"
    print("✓ Instruction artifacts removed correctly")
    
    # Test case 3: Clean text remains unchanged
    clean_text = "Microsoft is a technology company based in Redmond."
    cleaned = qg._clean_answer(clean_text)
    assert cleaned == clean_text, "Clean text should remain unchanged"
    print("✓ Clean text preserved correctly")


def test_evaluate_sufficiency():
    """Test sufficiency evaluation with gibberish detection."""
    print("\n=== Test: Evaluate Sufficiency ===")
    
    qg = QueryGenerator()
    
    # Test case 1: Valid sufficient answer
    valid_answer = "Microsoft Corporation is a multinational technology company headquartered in Redmond, Washington."
    is_sufficient = qg.evaluate_sufficiency(valid_answer)
    assert is_sufficient, "Valid answer should be sufficient"
    print("✓ Valid answer evaluated as sufficient")
    
    # Test case 2: INSUFFICIENT_DATA marker
    insufficient = "INSUFFICIENT_DATA"
    is_sufficient = qg.evaluate_sufficiency(insufficient)
    assert not is_sufficient, "INSUFFICIENT_DATA should not be sufficient"
    print("✓ INSUFFICIENT_DATA correctly evaluated as insufficient")
    
    # Test case 3: Too short
    too_short = "Microsoft"
    is_sufficient = qg.evaluate_sufficiency(too_short)
    assert not is_sufficient, "Too short answer should not be sufficient"
    print("✓ Too short answer evaluated as insufficient")
    
    # Test case 4: Gibberish
    gibberish = "NAME_CONGRAINING Ferminium infiltration JSONLeveraging"
    is_sufficient = qg.evaluate_sufficiency(gibberish)
    assert not is_sufficient, "Gibberish should not be sufficient"
    print("✓ Gibberish evaluated as insufficient")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Gibberish Detection and Answer Validation Tests")
    print("=" * 60)
    
    test_gibberish_detection()
    test_answer_cleaning()
    test_evaluate_sufficiency()
    
    print("\n" + "=" * 60)
    print("✓ All gibberish detection tests passed!")
    print("=" * 60)
    print("\nThese tests validate:")
    print("  - Gibberish pattern detection")
    print("  - Answer cleaning and artifact removal")
    print("  - Sufficiency evaluation with quality checks")
    print("  - Special character and prompt leakage detection")
