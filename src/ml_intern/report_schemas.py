"""Reality Report schema — Part 1 output contract.

Defines the structured report format for the Context Intake + Repo Reality
Report. This is the foundational data contract for the research console's
inspection capability.

All models use Pydantic v2. All enums use Python's StrEnum for clean
JSON serialization. No model in this file contains recommendation,
priority, severity, or action fields.

Redaction contract:
    All text-bearing fields (summary, notes, snippet, detail, text,
    summary_text) are part of the visible report output. Producers of
    report data MUST redact sensitive material — including .env values,
    API keys, tokens, and provider secrets — before populating these
    fields. Raw secrets must never appear in report output. The existing
    ml_intern.security.redact_secrets() function provides the redaction
    layer. This contract does not implement redaction; it requires it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class DocumentRole(StrEnum):
    """Role a document plays in the project ecosystem."""

    SOURCE_OF_INTENT = "source_of_intent"
    OPERATIONAL_HISTORY = "operational_history"
    ARCHITECTURAL_REFERENCE = "architectural_reference"
    BEHAVIORAL_SPEC = "behavioral_spec"
    OTHER = "other"


class SourceKind(StrEnum):
    """What kind of source produced an observation or evidence item."""

    FILE_PRESENCE = "file_presence"
    DIRECTORY_STRUCTURE = "directory_structure"
    FILE_CONTENT = "file_content"
    CONFIG_VALUE = "config_value"
    DEPENDENCY = "dependency"
    GIT_STATE = "git_state"
    ENVIRONMENT = "environment"
    COMMAND_SURFACE = "command_surface"


class ObservationGranularity(StrEnum):
    """At what level of detail was something observed."""

    FILE_LEVEL = "file_level"
    DIRECTORY_LEVEL = "directory_level"
    CONFIG_LEVEL = "config_level"
    CODE_LEVEL = "code_level"
    CONTENT_LEVEL = "content_level"
    INTERFACE_LEVEL = "interface_level"


class FindingCategory(StrEnum):
    """Classification of a finding.

    Derived from PROJECT_CHARTER.md Section 8 plus 'aligned'.
    """

    ALIGNED = "aligned"
    MISALIGNMENT = "misalignment"
    MISSING_DECISION = "missing_decision"
    INCOMPLETE_IMPLEMENTATION = "incomplete_implementation"
    PHASE_DRIFT = "phase_drift"
    RESEARCH_GAP = "research_gap"
    STRUCTURAL_INCONSISTENCY = "structural_inconsistency"


class EvidenceOrigin(StrEnum):
    """Whether evidence comes from documents, repo state, or both."""

    DOCUMENT_BASED = "document_based"
    REPO_BASED = "repo_based"
    MIXED = "mixed"


class CompletenessStatus(StrEnum):
    """Whether the report generation completed fully."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class ProjectPhase(StrEnum):
    """Project phase position at report generation time.

    Used in the report envelope to contextualize findings against
    phase expectations. Prevents typo risk and ad hoc string values.
    """

    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_2_5 = "phase_2_5"
    BETWEEN_2_5_AND_3 = "between_2_5_and_3"
    PHASE_3 = "phase_3"
    PHASE_4 = "phase_4"
    PHASE_5 = "phase_5"
    PHASE_6 = "phase_6"
    PHASE_7 = "phase_7"
    OTHER = "other"


class ScanMode(StrEnum):
    """How this report was generated relative to previous reports.

    Supports future snapshot/diff awareness without implementing
    comparison logic in Part 1.
    """

    FULL = "full"
    BASELINE = "baseline"
    INCREMENTAL = "incremental"
    COMPARE = "compare"


# ══════════════════════════════════════════════════════════════════
# Supporting Models
# ══════════════════════════════════════════════════════════════════


class RepoIdentity(BaseModel):
    """Identity of a repository targeted by the report."""

    name: str = Field(description="Short repo name (e.g. 'lex_study_foundation')")
    local_path: str = Field(description="Absolute local filesystem path")
    remote_url: str | None = Field(
        default=None,
        description="Expected GitHub remote URL",
    )


class EvidenceItem(BaseModel):
    """A single piece of traceable evidence supporting a finding.

    Each item identifies its own repo, enabling cross-repo findings
    where evidence comes from both repositories.
    """

    repo: str = Field(description="Repo name this evidence belongs to")
    path: str | None = Field(
        default=None,
        description="File or directory path relative to repo root",
    )
    source_kind: SourceKind = Field(
        description="What kind of source produced this evidence",
    )
    snippet: str | None = Field(
        default=None,
        description="Extracted text or value that constitutes the evidence. "
        "Must be redacted — raw secrets must never appear in report output.",
    )
    notes: str | None = Field(
        default=None,
        description="Additional context about this evidence item. "
        "Must be redacted if derived from sensitive sources.",
    )


# ══════════════════════════════════════════════════════════════════
# Core Output Categories
# ══════════════════════════════════════════════════════════════════


class DocumentReadResult(BaseModel):
    """Result of reading a single project-defining document.

    Records what was targeted, whether it was found, what role it plays,
    and a summary of its contents. This is a 'what was read' record,
    not an interpretation.
    """

    id: str = Field(
        description="Report-scoped identifier (e.g. 'doc-001')",
        pattern=r"^doc-\d{3}$",
    )
    target_path: str = Field(
        description="Expected path relative to repo root (e.g. 'docs/PROJECT_CHARTER.md')",
    )
    repo: str = Field(description="Repo this document belongs to")
    role: DocumentRole = Field(description="What role this document plays")
    found: bool = Field(description="Whether the document was found at target_path")
    summary: str | None = Field(
        default=None,
        description="Concise summary of document contents (null if not found). "
        "Must be redacted — no raw secrets from document content.",
    )
    notes: str | None = Field(
        default=None,
        description="Document-specific observations or anomalies. "
        "Must be redacted if derived from sensitive content.",
    )
    last_modified: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of file's last modification (if available)",
    )


class Observation(BaseModel):
    """A directly observed fact from repo reality.

    Observations are raw facts — no judgment, no interpretation, no
    recommendation. They record what was seen, not what it means.
    Interpretation belongs in Finding.
    """

    id: str = Field(
        description="Report-scoped identifier (e.g. 'obs-001')",
        pattern=r"^obs-\d{3}$",
    )
    repo: str = Field(description="Repo where this was observed")
    paths: list[str] = Field(
        default_factory=list,
        description="Relevant file/directory paths relative to repo root",
    )
    source_kind: SourceKind = Field(
        description="What kind of source produced this observation",
    )
    granularity: ObservationGranularity = Field(
        description="At what level of detail this was observed",
    )
    description: str = Field(
        description="Factual description of what was observed — no interpretation",
    )


class Finding(BaseModel):
    """An interpreted conclusion derived from documents and/or observations.

    Every finding must be evidence-backed. Evidence is a list because a
    single finding may draw from multiple sources across both repos.
    Findings classify into explicit categories but never carry severity,
    priority, or recommended actions.
    """

    id: str = Field(
        description="Report-scoped identifier (e.g. 'fnd-001')",
        pattern=r"^fnd-\d{3}$",
    )
    category: FindingCategory = Field(
        description="Classification of this finding",
    )
    description: str = Field(
        description="Short, specific description of what was found. "
        "Must be redacted — no raw secrets.",
    )
    detail: str | None = Field(
        default=None,
        description="Optional elaboration with additional context. "
        "Must be redacted if referencing sensitive material.",
    )
    evidence: list[EvidenceItem] = Field(
        min_length=1,
        description="Evidence items backing this finding (at least one required)",
    )
    evidence_origin: EvidenceOrigin = Field(
        description="Whether evidence is document-based, repo-based, or mixed",
    )
    referenced_observations: list[str] = Field(
        default_factory=list,
        description="IDs of observations that support this finding (e.g. ['obs-001'])",
    )
    referenced_documents: list[str] = Field(
        default_factory=list,
        description="IDs of document read results related to this finding (e.g. ['doc-001'])",
    )


class QuestionRaised(BaseModel):
    """A question surfaced by the current state for human review.

    Questions are the bridge between inspection and discussion. They
    must be neutral, evidence-grounded, and must never contain solutions,
    recommendations, or prioritization. They ask 'what?' — never 'you should'.
    """

    id: str = Field(
        description="Report-scoped identifier (e.g. 'qst-001')",
        pattern=r"^qst-\d{3}$",
    )
    text: str = Field(
        description="The question itself — neutral, no recommendations embedded. "
        "Must be redacted if referencing sensitive material.",
    )
    triggered_by: list[str] = Field(
        min_length=1,
        description="IDs of findings, observations, or documents that triggered this question",
    )


class ExecutiveSummary(BaseModel):
    """Compact, readable snapshot of the report.

    Provides counts and a natural language paragraph. Must not contain
    action items, priorities, or 'next steps'.
    """

    repos_covered: list[str] = Field(
        description="Names of repos included in this report",
    )
    documents_read: int = Field(description="Total documents targeted")
    documents_found: int = Field(description="Documents successfully read")
    observations_count: int = Field(description="Total observations recorded")
    findings_by_category: dict[str, int] = Field(
        description="Count of findings per FindingCategory value",
    )
    questions_raised_count: int = Field(description="Total questions surfaced")
    summary_text: str = Field(
        description="One-paragraph natural language summary of the current state. "
        "Must be redacted — no raw secrets.",
    )


# ══════════════════════════════════════════════════════════════════
# Report Envelope
# ══════════════════════════════════════════════════════════════════


class RealityReport(BaseModel):
    """Top-level report envelope for the Context Intake + Repo Reality Report.

    Every report is self-describing: it carries its own metadata, the repos
    it targeted, the phase it was generated in, and all content sections.
    No report is ever a contextless collection of results.

    Snapshot awareness:
        report_id and snapshot_id support future diff/comparison workflows.
        scan_mode indicates how this report was generated. In Part 1, only
        'full' and 'baseline' are practically used. 'incremental' and
        'compare' become meaningful when snapshot persistence exists.
        compared_to_snapshot_id is null in Part 1 but reserved for future
        comparison reports.
    """

    # ── Identity ──
    report_id: str = Field(
        description="Unique report identifier (e.g. 'rpt-20260424-055000'). "
        "Human-readable, timestamp-based.",
        pattern=r"^rpt-\d{8}-\d{6}$",
    )

    # ── Metadata ──
    timestamp: str = Field(
        description="ISO 8601 timestamp of report generation",
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Version of the report schema format",
    )
    target_repos: list[RepoIdentity] = Field(
        description="Repositories targeted by this report",
    )
    current_phase: ProjectPhase = Field(
        description="Project phase at report generation time",
    )
    completeness: CompletenessStatus = Field(
        description="Whether the report generation completed fully",
    )

    # ── Snapshot Awareness ──
    snapshot_id: str | None = Field(
        default=None,
        description="Identifier for the repo state captured by this report. "
        "Used by future layers to track state over time.",
        pattern=r"^snp-\d{8}-\d{6}$",
    )
    scan_mode: ScanMode = Field(
        default=ScanMode.FULL,
        description="How this report was generated relative to previous reports",
    )
    compared_to_snapshot_id: str | None = Field(
        default=None,
        description="Snapshot ID this report is compared against (null if not a comparison). "
        "Reserved for future incremental/compare scan modes.",
        pattern=r"^snp-\d{8}-\d{6}$",
    )

    # ── Content Sections ──
    documents: list[DocumentReadResult] = Field(
        default_factory=list,
        description="Results of reading project-defining documents",
    )
    observations: list[Observation] = Field(
        default_factory=list,
        description="Directly observed facts from repo reality",
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Interpreted conclusions derived from evidence",
    )
    questions: list[QuestionRaised] = Field(
        default_factory=list,
        description="Questions surfaced for human review",
    )
    executive_summary: ExecutiveSummary = Field(
        description="Compact snapshot of the report",
    )
