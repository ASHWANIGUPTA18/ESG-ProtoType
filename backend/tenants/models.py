"""Tenant + User.

Tenant is modeled with the columns and indexes a real multi-tenant SaaS needs,
but no scoped manager / middleware is enforced. One tenant is seeded. The seam
is documented in TRADEOFFS.md and DECISIONS.md.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Tenant(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class User(AbstractUser):
    class Role(models.TextChoices):
        ANALYST = "analyst", "Analyst"
        ADMIN = "admin", "Admin"

    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="users", null=True, blank=True
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ANALYST)

    def __str__(self) -> str:
        return f"{self.username} [{self.role}]"
