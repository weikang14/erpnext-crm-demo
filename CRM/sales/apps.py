from django.apps import AppConfig
from django.db.models.signals import post_migrate

# what the sales manager may maintain in /admin/ (the CRM pages themselves check the group, not these)
MANAGER_ADMIN_PERMS = {
    "sales": {"product": "view add change", "lostreason": "view add change", "salesrep": "view add change"},
    "auth": {"user": "view add change"},
}


def ensure_manager_group(**kwargs):
    from django.contrib.auth.models import Group, Permission

    from sales.models import MANAGER_GROUP

    group, _ = Group.objects.get_or_create(name=MANAGER_GROUP)
    for app, models in MANAGER_ADMIN_PERMS.items():
        for model, actions in models.items():
            codenames = [f"{action}_{model}" for action in actions.split()]
            group.permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codenames))


class SalesConfig(AppConfig):
    name = "sales"
    verbose_name = "Sales"

    def ready(self):
        post_migrate.connect(ensure_manager_group, sender=self)  # after this app's permissions exist
