"""OpenTelemetry SDK bootstrap. No exporter wired in P0; spans emit in-process."""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from app.core.config import get_settings


def init_otel() -> None:
    settings = get_settings()
    resource = Resource.create({"service.name": settings.otel_service_name})
    trace.set_tracer_provider(TracerProvider(resource=resource))
