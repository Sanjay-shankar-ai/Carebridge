from fastapi import APIRouter
from app.api.v1.endpoints import (
    health,
    auth,
    cases,
    patients,
    appointments,
    referrals,
    recovery,
    agent,
    workflows,
    analytics,
    notifications,
    fhir,
    doctor_allocation,
    dashboards,
)

api_router = APIRouter()

# Mount all endpoint routers
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(cases.router)
api_router.include_router(patients.router)
api_router.include_router(appointments.router)
api_router.include_router(referrals.router)
api_router.include_router(recovery.router)
api_router.include_router(agent.router)
api_router.include_router(workflows.router)
api_router.include_router(analytics.router)
api_router.include_router(notifications.router)
api_router.include_router(fhir.router)
api_router.include_router(doctor_allocation.router)
api_router.include_router(dashboards.router)
