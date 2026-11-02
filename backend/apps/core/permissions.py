from rest_framework.permissions import BasePermission,SAFE_METHODS

class WorkspacePermission(BasePermission):
    """管理员可全部操作，业务角色分别控制编辑与复核。"""
    message='当前账号没有此操作权限，请联系管理员配置测试或复核角色。'
    def has_permission(self,request,view):
        user=request.user
        if not user or not user.is_authenticated:return False
        if user.is_superuser:return True
        if request.method in SAFE_METHODS:return True
        groups=set(user.groups.values_list('name',flat=True))
        action=getattr(view,'action','')
        if action=='approve' or getattr(view,'basename','')=='review':
            return '复核人员' in groups
        return '测试人员' in groups
