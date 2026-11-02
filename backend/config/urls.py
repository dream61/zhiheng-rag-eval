from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from apps.core.views import AssetViewSet, ExperimentViewSet, ReviewViewSet, RegressionViewSet, health, capabilities
router = DefaultRouter()
router.register("assets", AssetViewSet)
router.register("experiments", ExperimentViewSet)
router.register("reviews", ReviewViewSet)
router.register("regressions", RegressionViewSet)
urlpatterns = [path("admin/", admin.site.urls), path("api/health/", health), path("api/capabilities/", capabilities), path("api/token/", obtain_auth_token), path("api/", include(router.urls))]
