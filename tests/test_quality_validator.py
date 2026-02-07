"""
Unit tests for extraction quality validation.

Tests the ExtractionQualityValidator class and quality checking functionality.
"""

import pytest

from garuda_intel.extractor.quality_validator import (
    ExtractionQualityValidator,
    QualityIssue,
    QualityReport,
    IssueSeverity,
    IssueType
)


class TestQualityIssue:
    """Test QualityIssue dataclass."""
    
    def test_issue_creation(self):
        """Test creating a quality issue."""
        issue = QualityIssue(
            issue_type=IssueType.MISSING_CRITICAL_FIELD,
            severity=IssueSeverity.CRITICAL,
            field="basic_info",
            message="Missing basic information",
            current_value=None,
            suggested_fix={"description": "No description"}
        )
        
        assert issue.issue_type == IssueType.MISSING_CRITICAL_FIELD
        assert issue.severity == IssueSeverity.CRITICAL
        assert issue.field == "basic_info"


class TestQualityReport:
    """Test QualityReport dataclass."""
    
    def test_report_creation(self):
        """Test creating a quality report."""
        issues = [
            QualityIssue(
                issue_type=IssueType.DUPLICATE_DATA,
                severity=IssueSeverity.WARNING,
                field="persons",
                message="Duplicate persons"
            )
        ]
        
        report = QualityReport(
            overall_score=0.75,
            issues=issues,
            completeness_score=0.8,
            consistency_score=0.7,
            plausibility_score=0.75
        )
        
        assert report.overall_score == 0.75
        assert len(report.issues) == 1
    
    def test_has_critical_issues(self):
        """Test checking for critical issues."""
        # No critical issues
        report1 = QualityReport(
            overall_score=0.8,
            issues=[
                QualityIssue(
                    issue_type=IssueType.DUPLICATE_DATA,
                    severity=IssueSeverity.WARNING,
                    field="test",
                    message="Test"
                )
            ],
            completeness_score=0.8,
            consistency_score=0.8,
            plausibility_score=0.8
        )
        assert not report1.has_critical_issues
        
        # Has critical issue
        report2 = QualityReport(
            overall_score=0.5,
            issues=[
                QualityIssue(
                    issue_type=IssueType.MISSING_CRITICAL_FIELD,
                    severity=IssueSeverity.CRITICAL,
                    field="basic_info",
                    message="Missing basic info"
                )
            ],
            completeness_score=0.5,
            consistency_score=0.8,
            plausibility_score=0.8
        )
        assert report2.has_critical_issues
    
    def test_passed_property(self):
        """Test the passed property."""
        # Passed
        report1 = QualityReport(
            overall_score=0.8,
            issues=[],
            completeness_score=0.8,
            consistency_score=0.8,
            plausibility_score=0.8
        )
        assert report1.passed
        
        # Failed - low score
        report2 = QualityReport(
            overall_score=0.5,
            issues=[],
            completeness_score=0.5,
            consistency_score=0.8,
            plausibility_score=0.8
        )
        assert not report2.passed
        
        # Failed - critical issue
        report3 = QualityReport(
            overall_score=0.8,
            issues=[
                QualityIssue(
                    issue_type=IssueType.MISSING_CRITICAL_FIELD,
                    severity=IssueSeverity.CRITICAL,
                    field="test",
                    message="Test"
                )
            ],
            completeness_score=0.8,
            consistency_score=0.8,
            plausibility_score=0.8
        )
        assert not report3.passed


class TestExtractionQualityValidator:
    """Test ExtractionQualityValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return ExtractionQualityValidator(
            min_completeness_score=0.3,
            enable_auto_correction=True
        )
    
    def test_initialization(self, validator):
        """Test validator initialization."""
        assert validator.min_completeness_score == 0.3
        assert validator.enable_auto_correction is True
    
    def test_validate_complete_extraction(self, validator):
        """Test validation of complete extraction."""
        intel = {
            "basic_info": {"description": "Test company"},
            "persons": [{"name": "John Doe"}],
            "locations": [{"location": "New York"}],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company", "Company")
        
        assert report.overall_score > 0.5
        assert report.completeness_score > 0.5
        assert report.consistency_score >= 0.0
        assert report.plausibility_score >= 0.0
    
    def test_validate_missing_critical_field(self, validator):
        """Test validation catches missing critical fields."""
        intel = {
            "persons": [{"name": "John Doe"}],
            "locations": [],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company", "Company")
        
        # Should flag missing basic_info
        critical_issues = [i for i in report.issues if i.severity == IssueSeverity.CRITICAL]
        assert len(critical_issues) > 0
        assert any("basic_info" in i.field for i in critical_issues)
    
    def test_validate_low_completeness(self, validator):
        """Test validation of low completeness."""
        intel = {
            "basic_info": {},
            "persons": [],
            "locations": [],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company", "Company")
        
        assert report.completeness_score < 0.5
        assert len(report.issues) > 0
    
    def test_detect_duplicate_persons(self, validator):
        """Test detection of duplicate persons."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [
                {"name": "John Doe"},
                {"name": "John Doe"},  # Duplicate
                {"name": "Jane Smith"}
            ],
            "locations": [],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company")
        
        duplicate_issues = [i for i in report.issues if i.issue_type == IssueType.DUPLICATE_DATA]
        assert len(duplicate_issues) > 0
    
    def test_detect_future_founding_year(self, validator):
        """Test detection of implausible founding year."""
        intel = {
            "basic_info": {"founded": "2050"},  # Future year
            "persons": [],
            "locations": [],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company")
        
        plausibility_issues = [
            i for i in report.issues
            if i.issue_type == IssueType.IMPLAUSIBLE_VALUE
        ]
        assert len(plausibility_issues) > 0
    
    def test_detect_implausible_employee_count(self, validator):
        """Test detection of implausible employee count."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [],
            "locations": [],
            "metrics": [
                {"type": "employees", "value": "50000000"}  # 50 million employees
            ],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report = validator.validate(intel, "Test Company")
        
        plausibility_issues = [
            i for i in report.issues
            if "employee" in i.message.lower()
        ]
        assert len(plausibility_issues) > 0
    
    def test_handle_none_metric_type(self, validator):
        """Test that None type values in metrics don't cause AttributeError."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [],
            "locations": [],
            "metrics": [
                {"type": None, "value": "100"},  # None type should not crash
                {"type": "employees", "value": "500"},  # Valid metric
                {"value": "200"}  # Missing type key
            ],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        # Should not raise AttributeError
        report = validator.validate(intel, "Test Company")
        
        # Should complete validation without errors
        assert report is not None
        assert report.overall_score >= 0.0
    
    def test_auto_correct_missing_field(self, validator):
        """Test auto-correction of missing fields."""
        intel = {
            "persons": [],
            "locations": [],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        issues = [
            QualityIssue(
                issue_type=IssueType.MISSING_CRITICAL_FIELD,
                severity=IssueSeverity.CRITICAL,
                field="basic_info",
                message="Missing basic_info",
                suggested_fix={"description": "Test Company"}
            )
        ]
        
        corrected = validator.auto_correct(intel, issues)
        
        assert "basic_info" in corrected
        assert corrected["basic_info"] == {"description": "Test Company"}
    
    def test_auto_correct_removes_duplicates(self, validator):
        """Test that auto-correction removes duplicates."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [
                {"name": "John Doe", "role": "CEO"},
                {"name": "John Doe", "role": "Founder"},  # Duplicate name
                {"name": "Jane Smith", "role": "CTO"}
            ],
            "locations": [
                {"location": "New York"},
                {"location": "New York"},  # Duplicate
                {"location": "Boston"}
            ],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        corrected = validator.auto_correct(intel, [])
        
        # Should remove duplicate persons (by name)
        person_names = [p["name"] for p in corrected["persons"]]
        assert len(person_names) == len(set(person_names))
        
        # Should remove duplicate locations
        location_names = [loc["location"] for loc in corrected["locations"]]
        assert len(location_names) == len(set(location_names))
    
    def test_extract_year_from_string(self, validator):
        """Test extracting year from various formats."""
        assert validator._extract_year("Founded in 2020") == 2020
        assert validator._extract_year("1995") == 1995
        assert validator._extract_year(2018) == 2018
        assert validator._extract_year("No year here") is None
        assert validator._extract_year("") is None
    
    def test_extract_number_from_string(self, validator):
        """Test extracting numbers from various formats."""
        assert validator._extract_number("500") == 500
        assert validator._extract_number("1,234") == 1234
        assert validator._extract_number("5M") == 5_000_000
        assert validator._extract_number("2.5 million") == 2_500_000
        assert validator._extract_number("10K") == 10_000
        assert validator._extract_number("1.5B") == 1_500_000_000
        assert validator._extract_number("No number") is None
    
    def test_get_validation_summary(self, validator):
        """Test generating validation summary."""
        report = QualityReport(
            overall_score=0.75,
            issues=[
                QualityIssue(
                    issue_type=IssueType.DUPLICATE_DATA,
                    severity=IssueSeverity.WARNING,
                    field="persons",
                    message="Duplicate persons detected"
                )
            ],
            completeness_score=0.8,
            consistency_score=0.7,
            plausibility_score=0.75
        )
        
        summary = validator.get_validation_summary(report)
        
        assert "0.75" in summary
        assert "Completeness" in summary
        assert "Consistency" in summary
        assert "Plausibility" in summary
        assert "persons" in summary
    
    def test_validation_disabled_auto_correction(self):
        """Test validator with auto-correction disabled."""
        validator = ExtractionQualityValidator(enable_auto_correction=False)
        
        intel = {"persons": [{"name": "John"}, {"name": "John"}]}
        issues = []
        
        corrected = validator.auto_correct(intel, issues)
        
        # Should return unchanged intel
        assert corrected == intel
    
    def test_consistency_score_calculation(self, validator):
        """Test consistency score calculation."""
        # Good consistency
        intel1 = {
            "basic_info": {"description": "Test"},
            "persons": [{"name": "John"}, {"name": "Jane"}],
            "locations": [{"location": "NYC"}],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        report1 = validator.validate(intel1, "Test")
        assert report1.consistency_score >= 0.9
        
        # Poor consistency (many duplicates)
        intel2 = {
            "basic_info": {"description": "Test"},
            "persons": [{"name": "John"}, {"name": "John"}, {"name": "John"}],
            "locations": [{"location": "NYC"}, {"location": "NYC"}],
            "events": [
                {"description": "Event A"},
                {"description": "Event A"}
            ],
            "metrics": [],
            "financials": [],
            "products": [],
            "jobs": [],
            "relationships": []
        }
        
        report2 = validator.validate(intel2, "Test")
        assert report2.consistency_score < 0.9
    
    def test_handle_string_items_in_lists(self, validator):
        """Test that validator handles string items in lists that should contain dicts."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [
                "John Doe",  # String instead of dict
                {"name": "Jane Smith"},  # Normal dict
                "Bob Johnson"  # Another string
            ],
            "events": [
                "Event description",  # String instead of dict
                {"description": "Real event"}  # Normal dict
            ],
            "locations": [
                "New York",  # String instead of dict
                {"location": "Boston"}  # Normal dict
            ],
            "metrics": [],
            "financials": [],
            "products": [],
            "jobs": [],
            "relationships": []
        }
        
        # Should not raise AttributeError
        report = validator.validate(intel, "Test Company")
        
        # Should complete validation without errors
        assert report is not None
        assert report.overall_score >= 0.0
        assert report.consistency_score >= 0.0

    def test_remove_duplicates_with_string_items(self, validator):
        """Test that _remove_duplicates handles string items in lists without raising AttributeError."""
        intel = {
            "basic_info": {"description": "Test"},
            "persons": [
                "Satya Nadella",  # String item
                {"name": "Satya Nadella", "role": "CEO"},  # Dict with same name - should be deduped
                {"name": "Bill Gates", "role": "Founder"},
                "Bill Gates",  # String duplicate - should be deduped
            ],
            "locations": [
                "New York",  # String item
                {"location": "New York"},  # Dict with same location - should be deduped
                "Boston",
            ],
            "metrics": [],
            "financials": [],
            "products": [],
            "events": [],
            "jobs": [],
            "relationships": []
        }
        
        # Should not raise AttributeError when calling auto_correct
        corrected = validator.auto_correct(intel, [])
        
        # Should complete without errors
        assert corrected is not None
        
        # Should have deduplicated persons (by name, case-insensitive)
        assert len(corrected["persons"]) == 2  # Satya Nadella and Bill Gates
        
        # Should have deduplicated locations
        assert len(corrected["locations"]) == 2  # New York and Boston
