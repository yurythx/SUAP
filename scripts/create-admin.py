import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "suap.settings")
django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
u, created = User.objects.get_or_create(username="admin")
for attr, val in [("is_staff", True), ("is_superuser", True), ("is_active", True)]:
    if hasattr(u, attr):
        setattr(u, attr, val)
u.set_password(os.environ["SUAP_ADMIN_PASSWORD"])
u.save()
print("USER", "created" if created else "updated", getattr(u, "pk", None))
