from django.contrib import admin
from .models import Asset, Experiment, Result, Review

class ReadOnlyBusinessAdmin(admin.ModelAdmin):
    """业务记录统一通过API修改，管理后台只读。"""
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

for model in (Asset, Experiment, Result, Review):
    admin.site.register(model, ReadOnlyBusinessAdmin)
