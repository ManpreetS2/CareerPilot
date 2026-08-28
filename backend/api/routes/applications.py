"""Application materials + Approval Agent routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user, get_extension_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.schemas import (
    GenerateMaterialsRequest,
    ApplicationPackage,
    ApprovalRequest,
    ApprovalResponse,
    AutofillResponse,
    CreateResumeVersionRequest,
    ExtensionPanelData,
    ExtensionResumeVersion,
    ExtensionResumeVersionList,
    FormFillResult,
    IngestJobUrlRequest,
    Job,
    MatchScore,
    ResumeVersion,
    ResumeVersionDetail,
    ResumeVersionSummary,
)
from backend.services.application_service import (
    StoredMaterialsNotFoundError,
    apply_approval,
    discard_stale_reviewed_package,
    get_or_generate_application_package,
    get_stored_application_package,
)
from backend.services.application_materials_agent import StaleApplicationMaterialsError
from backend.services.form_fill_service import (
    find_job_by_url,
    get_autofill_data,
    get_extension_panel_data,
    run_assisted_apply,
)
from backend.services.job_scout_service import JobScoutError, ingest_job_url, normalize_job, persist_jobs
from backend.services.job_service import record_to_job
from backend.services.saved_job_service import save_job, unsave_job
from backend.services.url_safety import UnsafeURLError
from backend.services.analysis_service import load_job
from backend.services.scoring_orchestrator import score_job_with_intelligence
from backend.services.verified_fit_service import score_job_verified
from backend.services.resume_version_service import (
    ResumeVersionConflictError,
    ResumeVersionNotFoundError,
    ResumeVersionPersistenceError,
    export_owned_resume_version,
    get_resume_version,
    get_user_resume_version,
    list_resume_versions,
    list_user_resume_versions,
    save_resume_version,
)
from backend.services.resume_export import InvalidResumeExportFormatError, ResumeExportError

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/jobs/{job_id}/materials", response_model=ApplicationPackage)
def get_materials(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationPackage:
    """Return stored grounded materials. Never generates, writes, or calls a provider."""
    try:
        return get_stored_application_package(db, job_id, user.id)
    except StoredMaterialsNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StaleApplicationMaterialsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/generate-materials", response_model=ApplicationPackage)
def generate_materials(
    job_id: str,
    request: Request,
    payload: GenerateMaterialsRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationPackage:
    """Generate grounded application materials after an explicit user action.

    override_grounding must be sent deliberately in the request body for the
    one job being generated. It is never implied by any other field and is
    not remembered between requests, so applying to a stretch role cannot
    quietly become the default for every later application.
    """
    generator = getattr(request.app.state, "application_materials_generator", None)
    return get_or_generate_application_package(
        db,
        job_id,
        user.id,
        generator=generator,
        override_grounding=bool(payload and payload.override_grounding),
    )


@router.post("/jobs/{job_id}/discard-stale-materials")
def discard_stale_materials(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Explicit owner-only reset of reviewed materials from a previous profile."""
    return discard_stale_reviewed_package(db, job_id, user.id)


@router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
def approve_materials(
    job_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return apply_approval(db, job_id, user.id, payload)


def _http_for_resume_version_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResumeVersionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ResumeVersionConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ResumeVersionPersistenceError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save resume version.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to save resume version.",
    )


@router.post("/jobs/{job_id}/resume-versions", response_model=ResumeVersion)
def create_resume_version_route(
    job_id: str,
    payload: CreateResumeVersionRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersion:
    """Snapshot the current approved package. Never generates materials or calls an LLM."""
    _ = payload
    try:
        version, created = save_resume_version(db, job_id, user.id)
    except (
        ResumeVersionNotFoundError,
        ResumeVersionConflictError,
        ResumeVersionPersistenceError,
    ) as exc:
        raise _http_for_resume_version_error(exc) from exc
    if created:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=version.model_dump(mode="json"),
        )
    return version


@router.get("/jobs/{job_id}/resume-versions", response_model=list[ResumeVersion])
def list_resume_versions_route(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeVersion]:
    """List the current user's resume versions for one job. Never writes or generates."""
    try:
        return list_resume_versions(db, job_id, user.id)
    except ResumeVersionNotFoundError as exc:
        raise _http_for_resume_version_error(exc) from exc


@router.get("/jobs/{job_id}/resume-versions/{version_id}", response_model=ResumeVersion)
def get_resume_version_route(
    job_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersion:
    """Return one owned resume version. Cross-user access is a sanitized 404."""
    try:
        return get_resume_version(db, job_id, version_id, user.id)
    except ResumeVersionNotFoundError as exc:
        raise _http_for_resume_version_error(exc) from exc


@router.get("/resume-versions", response_model=list[ResumeVersionSummary])
def list_all_resume_versions_route(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeVersionSummary]:
    """List the current user's resume versions across jobs. Never writes or generates."""
    return list_user_resume_versions(db, user.id)


@router.get("/resume-versions/{version_id}", response_model=ResumeVersionDetail)
def get_user_resume_version_route(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersionDetail:
    """Return one owned historical resume version. Cross-user access is a sanitized 404."""
    try:
        return get_user_resume_version(db, version_id, user.id)
    except ResumeVersionNotFoundError as exc:
        raise _http_for_resume_version_error(exc) from exc


@router.post("/jobs/{job_id}/fill-application", response_model=FormFillResult)
def fill_application(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FormFillResult:
    """Assisted apply: fills a real Greenhouse/Lever form with what can be
    confidently mapped from the approved application package, flags
    anything it can't map, and never submits. Requires the application to
    already be approved."""
    return run_assisted_apply(db, job_id, user.id)


@router.get("/extension/autofill", response_model=AutofillResponse)
def extension_autofill(
    url: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> AutofillResponse:
    """Field values for the browser extension. Authenticated only via the
    extension session header, not as a general alternative to the cookie."""
    return get_autofill_data(db, url, user.id)


@router.get("/extension/panel-data", response_model=ExtensionPanelData)
def extension_panel_data(
    url: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> ExtensionPanelData:
    """Read-only job/score/materials status for the extension side panel.
    Same auth as the autofill route above — a second GET-only route inside
    the same /api/extension/ prefix does not expand what the session header
    can authorize. Unlike autofill, never requires an approved package."""
    return get_extension_panel_data(db, url, user.id)


@router.post("/extension/ingest-url", response_model=Job, status_code=status.HTTP_201_CREATED)
def extension_ingest_url(
    payload: IngestJobUrlRequest, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> Job:
    """Find the canonical stored job or ingest once. Never duplicates."""
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")
    existing = find_job_by_url(db, url)
    if existing is not None:
        return record_to_job(existing)
    try:
        raw = ingest_job_url(url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="URL is malformed.") from exc
    except JobScoutError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    stored = persist_jobs([normalize_job(raw, "manual")])
    return stored[0]


@router.post("/extension/jobs/{job_id}/save", response_model=Job)
def extension_save_job(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> Job:
    return save_job(db, user.id, job_id).job


@router.delete("/extension/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def extension_unsave_job(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> Response:
    unsave_job(db, user.id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/extension/jobs/{job_id}/verified-fit", response_model=MatchScore)
def extension_verified_fit(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> MatchScore:
    """Run full-job Verified Fit. The panel must not call this on open."""
    from backend.api.routes.scoring import _http_for_intelligence_error, _http_for_scoring_error, _is_intelligence_pipeline_error

    try:
        score_job_with_intelligence(db, job_id, user.id)
        job = load_job(db, job_id)
        return score_job_verified(db, job, user.id)
    except Exception as exc:  # noqa: BLE001
        if _is_intelligence_pipeline_error(exc):
            raise _http_for_intelligence_error(exc) from exc
        raise _http_for_scoring_error(exc) from exc


@router.get("/extension/resume-versions", response_model=ExtensionResumeVersionList)
def extension_list_resume_versions(
    job_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_extension_user),
) -> ExtensionResumeVersionList:
    """Metadata only. Never downloads document bytes on list."""
    versions = [
        ExtensionResumeVersion(**item.model_dump(), formats=["pdf", "docx"])
        for item in list_user_resume_versions(db, user.id)
    ]
    return ExtensionResumeVersionList(versions=versions, current_job_id=job_id)


@router.get("/extension/resume-versions/{version_id}/file")
def extension_resume_version_file(
    version_id: str,
    format: str = Query(default="pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_extension_user),
) -> Response:
    """Ownership-checked PDF/DOCX download. Format is an allowlist, not a path."""
    try:
        payload, mime, filename = export_owned_resume_version(db, version_id, user.id, format)
    except InvalidResumeExportFormatError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported export format.")
    except ResumeVersionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume version not found.")
    except ResumeExportError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resume export is unavailable.")
    return Response(
        content=payload,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
