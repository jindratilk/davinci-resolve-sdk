"""Product-facing guidance for services provided by the CutAgent desktop app."""

from __future__ import annotations

from .errors import HostedServiceRequiresCutAgentApp


LANDING_PAGE_URL = "https://cutagent.ai"

_SERVICES = {
    "voice_catalog": ("AI voice selection", "AI voice selection is available in the CutAgent desktop app."),
    "voice_generation": ("AI voice generation", "AI voice generation is available in the CutAgent desktop app."),
    "transcription": ("AI transcription", "AI transcription is available in the CutAgent desktop app."),
    "video_generation": ("AI video generation", "AI video generation is available in the CutAgent desktop app."),
}


def unavailable(service_key: str) -> None:
    """Raise before authentication, billing, upload, download, or provider I/O."""
    service, message = _SERVICES[service_key]
    raise HostedServiceRequiresCutAgentApp(
        f"{message} Explore plans: {LANDING_PAGE_URL}.",
        details={
            "service": service,
            "distribution": "standalone_local",
            "landing_page_url": LANDING_PAGE_URL,
            "network_attempted": False,
            "upload_attempted": False,
            "billing_attempted": False,
            "authentication_attempted": False,
        },
        suggested_fix=f"Explore the CutAgent desktop app at {LANDING_PAGE_URL}.",
    )
