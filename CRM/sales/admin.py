from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from sales.models import LostReason, Product, SalesRep


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["item_code", "name", "uom", "list_price", "active"]
    list_filter = ["active"]
    search_fields = ["item_code", "name"]


@admin.register(LostReason)
class LostReasonAdmin(admin.ModelAdmin):
    list_display = ["name", "active"]


@admin.register(SalesRep)
class SalesRepAdmin(admin.ModelAdmin):
    list_display = ["user", "region", "active"]
    list_filter = ["region", "active"]


admin.site.unregister(User)


@admin.register(User)
class GuardedUserAdmin(UserAdmin):
    """The manager onboards and deactivates reps here; only a superuser grants admin rights or edits a superuser."""

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return fields
        return [*fields, "is_staff", "is_superuser", "groups", "user_permissions"]

    def has_change_permission(self, request, obj=None):  # also guards the password view
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)


admin.site.site_header = "Ombak CRM admin"
admin.site.site_title = "Ombak CRM admin"
