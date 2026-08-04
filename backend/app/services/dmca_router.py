"""DMCA reporting router — endpoint for copyright takedown requests.

Provides a POST /report endpoint that logs the request, tries to delete the reported file
from the results directory, and returns a unique report ID.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid, os, logging

router = APIRouter(tags=["dmca"])
logger = logging.getLogger(__name__)

class DMCAReport(BaseModel):
    url: str            # URL of the infringing file (typically under /results)
    infringer: str      # Name / identifier of the alleged infringer
    description: str    # Brief description of the infringement

@router.post("/report")
async def report_dmca(report: DMCAReport):
    """Accept a DMCA takedown request, log it, and delete the reported file if present.
    Returns a JSON with a newly generated report ID.
    """
    report_id = str(uuid.uuid4())
    logger.info(f"DMCA {report_id}: {report.json()}")
    # Try to delete the file from the results directory
    results_dir = os.getenv("RESULTS_DIR", "backend/results")
    try:
        os.remove(os.path.join(results_dir, os.path.basename(report.url)))
        logger.info(f"Removed DMCA‑reported file: {report.url}")
    except FileNotFoundError:
        logger.warning(f"DMCA file not found for removal: {report.url}")
    except Exception as exc:
        logger.exception(f"Error while removing DMCA file: {exc}")
    return {"status": "submitted", "id": report_id}
