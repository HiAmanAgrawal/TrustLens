"""
API v1 router aggregator.

Mount every endpoint module here; prefix and tags are set once so they
don't drift between the router file and the individual endpoint files.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    grocery,
    health_profiles,
    medicines,
    prescriptions,
    reactions,
    reminders,
    reports,
    scan,
    users,
)

router = APIRouter(prefix="/v1")

router.include_router(users.router,           prefix="/users",         tags=["users"])
router.include_router(health_profiles.router, prefix="/users",         tags=["health-profiles"])
router.include_router(reactions.router,       prefix="/users",         tags=["reactions"])
router.include_router(reminders.router,       prefix="/users",         tags=["reminders"])
router.include_router(medicines.router,       prefix="/medicines",     tags=["medicines"])
router.include_router(grocery.router,         prefix="/grocery",       tags=["grocery"])
router.include_router(prescriptions.router,   prefix="/prescriptions", tags=["prescriptions"])
router.include_router(scan.router,            prefix="/scan",          tags=["scan"])
router.include_router(reports.router,         prefix="/reports",       tags=["community-reports"])
