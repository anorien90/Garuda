"""
Extraction quality validation and auto-correction.

Validates extracted intelligence for completeness, consistency, and plausibility,
with automatic correction of common issues.
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IssueSeverity(str, Enum):
    """Severity levels for quality issues."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IssueType(str, Enum):
    """Types of quality issues."""
    MISSING_CRITICAL_FIELD = "missing_critical_field"
    INCONSISTENT_DATA = "inconsistent_data"
    IMPLAUSIBLE_VALUE = "implausible_value"
    INVALID_FORMAT = "invalid_format"
    DUPLICATE_DATA = "duplicate_data"
    LOW_CONFIDENCE = "low_confidence"


@dataclass
class QualityIssue:
    """Represents a quality issue in extracted data."""
    issue_type: IssueType
    severity: IssueSeverity
    field: str
    message: str
    current_value: Any = None
    suggested_fix: Any = None
    

@dataclass
class QualityReport:
    """Report on extraction quality."""
    overall_score: float  # 0.0 to 1.0
    issues: List[QualityIssue]
    completeness_score: float
    consistency_score: float
    plausibility_score: float
    
    @property
    def has_critical_issues(self) -> bool:
        """Check if report has any critical issues."""
        return any(issue.severity == IssueSeverity.CRITICAL for issue in self.issues)
    
    @property
    def passed(self) -> bool:
        """Check if extraction passed quality checks."""
        return self.overall_score >= 0.6 and not self.has_critical_issues


class ExtractionQualityValidator:
    """
    Validates quality of extracted intelligence.
    
    Checks for completeness, consistency, plausibility, and common errors,
    with automatic correction capabilities.
    """
    
    def __init__(
        self,
        min_completeness_score: float = 0.3,
        enable_auto_correction: bool = True
    ):
        """
        Initialize quality validator.
        
        Args:
            min_completeness_score: Minimum acceptable completeness (0.0 to 1.0)
            enable_auto_correction: Whether to attempt automatic corrections
        """
        self.min_completeness_score = min_completeness_score
        self.enable_auto_correction = enable_auto_correction
        self.logger = logging.getLogger(__name__)
        
        # Critical fields that should be present
        self.critical_fields = {'basic_info'}
    
    def validate(
        self,
        extracted_intel: Dict[str, Any],
        entity_name: str,
        entity_type: Optional[str] = None
    ) -> QualityReport:
        """
        Validate extracted intelligence.
        
        Args:
            extracted_intel: The extracted intelligence data
            entity_name: Name of the entity
            entity_type: Type of the entity (optional)
            
        Returns:
            Quality report with issues and scores
        """
        issues: List[QualityIssue] = []
        
        # Check completeness
        completeness_score, completeness_issues = self._check_completeness(
            extracted_intel,
            entity_name
        )
        issues.extend(completeness_issues)
        
        # Check consistency
        consistency_score, consistency_issues = self._check_consistency(
            extracted_intel,
            entity_name
        )
        issues.extend(consistency_issues)
        
        # Check plausibility
        plausibility_score, plausibility_issues = self._check_plausibility(
            extracted_intel,
            entity_type
        )
        issues.extend(plausibility_issues)
        
        # Calculate overall score
        overall_score = (
            completeness_score * 0.4 +
            consistency_score * 0.3 +
            plausibility_score * 0.3
        )
        
        report = QualityReport(
            overall_score=overall_score,
            issues=issues,
            completeness_score=completeness_score,
            consistency_score=consistency_score,
            plausibility_score=plausibility_score
        )
        
        self.logger.info(
            f"Quality validation: score={overall_score:.2f}, "
            f"issues={len(issues)}, critical={report.has_critical_issues}"
        )
        
        return report
    
    def _check_completeness(
        self,
        extracted_intel: Dict[str, Any],
        entity_name: str
    ) -> tuple[float, List[QualityIssue]]:
        """
        Check completeness of extracted data.
        
        Returns:
            (score, issues) tuple
        """
        issues = []
        
        # Check for critical fields
        if not extracted_intel.get('basic_info'):
            issues.append(QualityIssue(
                issue_type=IssueType.MISSING_CRITICAL_FIELD,
                severity=IssueSeverity.CRITICAL,
                field='basic_info',
                message='Missing basic_info section',
                suggested_fix={'description': f'No description available for {entity_name}'}
            ))
        
        # Count populated sections
        sections = [
            'basic_info', 'persons', 'jobs', 'metrics',
            'locations', 'financials', 'products', 'events', 'relationships'
        ]
        
        populated = sum(
            1 for section in sections
            if extracted_intel.get(section)
        )
        
        # Score based on number of populated sections (at least 3 is good)
        score = min(1.0, populated / 3.0)
        
        if score < self.min_completeness_score:
            issues.append(QualityIssue(
                issue_type=IssueType.MISSING_CRITICAL_FIELD,
                severity=IssueSeverity.WARNING,
                field='overall',
                message=f'Low completeness: only {populated}/{len(sections)} sections populated',
            ))
        
        return score, issues
    
    def _check_consistency(
        self,
        extracted_intel: Dict[str, Any],
        entity_name: str
    ) -> tuple[float, List[QualityIssue]]:
        """
        Check consistency of extracted data.
        
        Looks for contradictions and duplicates.
        
        Returns:
            (score, issues) tuple
        """
        issues = []
        score = 1.0
        
        # Check for duplicate persons
        persons = extracted_intel.get('persons', [])
        if persons:
            person_names = [p.get('name', '').lower() for p in persons if p.get('name')]
            if len(person_names) != len(set(person_names)):
                issues.append(QualityIssue(
                    issue_type=IssueType.DUPLICATE_DATA,
                    severity=IssueSeverity.WARNING,
                    field='persons',
                    message='Duplicate person names detected',
                ))
                score -= 0.1
        
        # Check for duplicate events
        events = extracted_intel.get('events', [])
        if events:
            event_descs = [
                e.get('description', '').lower()[:50]
                for e in events if e.get('description')
            ]
            if len(event_descs) != len(set(event_descs)):
                issues.append(QualityIssue(
                    issue_type=IssueType.DUPLICATE_DATA,
                    severity=IssueSeverity.INFO,
                    field='events',
                    message='Potential duplicate events detected',
                ))
                score -= 0.05
        
        # Check for duplicate locations
        locations = extracted_intel.get('locations', [])
        if locations:
            location_names = [
                loc.get('location', '').lower()
                for loc in locations if loc.get('location')
            ]
            if len(location_names) != len(set(location_names)):
                issues.append(QualityIssue(
                    issue_type=IssueType.DUPLICATE_DATA,
                    severity=IssueSeverity.INFO,
                    field='locations',
                    message='Duplicate locations detected',
                ))
                score -= 0.05
        
        return max(0.0, score), issues
    
    def _check_plausibility(
        self,
        extracted_intel: Dict[str, Any],
        entity_type: Optional[str]
    ) -> tuple[float, List[QualityIssue]]:
        """
        Check plausibility of extracted values.
        
        Returns:
            (score, issues) tuple
        """
        issues = []
        score = 1.0
        current_year = datetime.now().year
        
        # Check founding year in basic_info
        basic_info = extracted_intel.get('basic_info', {})
        if 'founded' in basic_info or 'founded_year' in basic_info:
            year_str = basic_info.get('founded') or basic_info.get('founded_year')
            year = self._extract_year(year_str)
            
            if year:
                # Year should be between 1800 and current year
                if year > current_year:
                    issues.append(QualityIssue(
                        issue_type=IssueType.IMPLAUSIBLE_VALUE,
                        severity=IssueSeverity.WARNING,
                        field='basic_info.founded',
                        message=f'Founding year {year} is in the future',
                        current_value=year_str,
                        suggested_fix=None
                    ))
                    score -= 0.2
                elif year < 1800:
                    issues.append(QualityIssue(
                        issue_type=IssueType.IMPLAUSIBLE_VALUE,
                        severity=IssueSeverity.WARNING,
                        field='basic_info.founded',
                        message=f'Founding year {year} seems too old',
                        current_value=year_str,
                    ))
                    score -= 0.1
        
        # Check event years
        events = extracted_intel.get('events', [])
        for event in events:
            if 'year' in event:
                year = self._extract_year(event.get('year'))
                if year and (year > current_year + 10 or year < 1900):
                    issues.append(QualityIssue(
                        issue_type=IssueType.IMPLAUSIBLE_VALUE,
                        severity=IssueSeverity.INFO,
                        field='events.year',
                        message=f'Event year {year} seems implausible',
                        current_value=event.get('year'),
                    ))
                    score -= 0.05
        
        # Check employee count
        metrics = extracted_intel.get('metrics', [])
        for metric in metrics:
            if 'employees' in metric.get('type', '').lower():
                value_str = metric.get('value', '')
                value = self._extract_number(value_str)
                
                if value and value > 10_000_000:  # > 10 million employees
                    issues.append(QualityIssue(
                        issue_type=IssueType.IMPLAUSIBLE_VALUE,
                        severity=IssueSeverity.WARNING,
                        field='metrics.employees',
                        message=f'Employee count {value:,} seems implausibly high',
                        current_value=value_str,
                    ))
                    score -= 0.1
        
        return max(0.0, score), issues
    
    def auto_correct(
        self,
        extracted_intel: Dict[str, Any],
        issues: List[QualityIssue]
    ) -> Dict[str, Any]:
        """
        Attempt automatic correction of issues.
        
        Args:
            extracted_intel: The extracted intelligence
            issues: List of quality issues
            
        Returns:
            Corrected intelligence data
        """
        if not self.enable_auto_correction:
            return extracted_intel
        
        corrected = extracted_intel.copy()
        corrections_made = 0
        
        for issue in issues:
            if issue.suggested_fix is not None:
                # Apply suggested fix
                if '.' in issue.field:
                    # Nested field
                    parts = issue.field.split('.')
                    if parts[0] not in corrected:
                        corrected[parts[0]] = {}
                    corrected[parts[0]][parts[1]] = issue.suggested_fix
                else:
                    # Top-level field
                    corrected[issue.field] = issue.suggested_fix
                
                corrections_made += 1
                self.logger.debug(f"Auto-corrected {issue.field}: {issue.message}")
        
        # Remove duplicates
        corrected = self._remove_duplicates(corrected)
        
        if corrections_made > 0:
            self.logger.info(f"Applied {corrections_made} automatic corrections")
        
        return corrected
    
    def _remove_duplicates(self, intel: Dict[str, Any]) -> Dict[str, Any]:
        """Remove duplicate entries from lists."""
        corrected = intel.copy()
        
        # Remove duplicate persons (by name)
        if 'persons' in corrected and corrected['persons']:
            seen_names = set()
            unique_persons = []
            for person in corrected['persons']:
                name = person.get('name', '').lower()
                if name and name not in seen_names:
                    seen_names.add(name)
                    unique_persons.append(person)
            corrected['persons'] = unique_persons
        
        # Remove duplicate locations (by location name)
        if 'locations' in corrected and corrected['locations']:
            seen_locations = set()
            unique_locations = []
            for loc in corrected['locations']:
                location = loc.get('location', '').lower()
                if location and location not in seen_locations:
                    seen_locations.add(location)
                    unique_locations.append(loc)
            corrected['locations'] = unique_locations
        
        return corrected
    
    def _extract_year(self, value: Any) -> Optional[int]:
        """Extract year from various formats."""
        if not value:
            return None
        
        # Try direct conversion
        if isinstance(value, int):
            return value
        
        if isinstance(value, str):
            # Look for 4-digit year
            match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', value)
            if match:
                return int(match.group(1))
        
        return None
    
    def _extract_number(self, value: Any) -> Optional[float]:
        """Extract numeric value from various formats."""
        if not value:
            return None
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # Remove common separators and units
            cleaned = value.lower()
            
            # Handle abbreviations (5M = 5 million, 2.5K = 2500)
            multiplier = 1
            if 'b' in cleaned or 'billion' in cleaned:
                multiplier = 1_000_000_000
                cleaned = re.sub(r'[b]illion?', '', cleaned)
            elif 'm' in cleaned or 'million' in cleaned:
                multiplier = 1_000_000
                cleaned = re.sub(r'[m]illion?', '', cleaned)
            elif 'k' in cleaned or 'thousand' in cleaned:
                multiplier = 1_000
                cleaned = re.sub(r'[k]|thousand', '', cleaned)
            
            # Remove commas and other separators
            cleaned = re.sub(r'[,\s]', '', cleaned)
            
            # Extract number
            match = re.search(r'[\d.]+', cleaned)
            if match:
                try:
                    return float(match.group()) * multiplier
                except ValueError:
                    pass
        
        return None
    
    def get_validation_summary(self, report: QualityReport) -> str:
        """
        Get human-readable summary of validation report.
        
        Args:
            report: Quality report
            
        Returns:
            Summary string
        """
        lines = [
            f"Quality Score: {report.overall_score:.2f}",
            f"Completeness: {report.completeness_score:.2f}",
            f"Consistency: {report.consistency_score:.2f}",
            f"Plausibility: {report.plausibility_score:.2f}",
            f"Issues: {len(report.issues)} ({len([i for i in report.issues if i.severity == IssueSeverity.CRITICAL])} critical)",
            f"Status: {'PASSED' if report.passed else 'FAILED'}",
        ]
        
        if report.issues:
            lines.append("\nIssues:")
            for issue in report.issues[:5]:  # Show first 5
                lines.append(f"  [{issue.severity.value}] {issue.field}: {issue.message}")
            
            if len(report.issues) > 5:
                lines.append(f"  ... and {len(report.issues) - 5} more")
        
        return "\n".join(lines)
