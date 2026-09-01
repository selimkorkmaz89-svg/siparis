from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from accounts.forms import (
    EmailLoginForm,
    ProfileForm,
    RegistrationForm,
    RejectUserForm,
    UserAdminForm,
)
from core.constants import Role, UserStatus
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from notifications import services as notify

User = get_user_model()


class AppLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        language = self.request.user.language
        if language:
            translation.activate(language)
            response.set_cookie("siparis_language", language)
        return response


class AppLogoutView(LogoutView):
    pass


def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        notify.user_registered(user)
        messages.success(
            request,
            _(
                "Your registration has been received. You can sign in once an "
                "administrator approves your account."
            ),
        )
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST" and "save_profile" in request.POST and form.is_valid():
        user = form.save()
        translation.activate(user.language)
        response = redirect("accounts:profile")
        response.set_cookie("siparis_language", user.language)
        messages.success(request, _("Your profile has been updated."))
        return response
    if request.method == "POST" and "change_password" in request.POST:
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, password_form.user)
            messages.success(request, _("Your password has been changed."))
            return redirect("accounts:profile")
    for field in password_form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")
    return render(
        request,
        "accounts/profile.html",
        {"form": form, "password_form": password_form},
    )


@role_required(Role.ADMIN)
def pending_users(request):
    queryset = User.objects.filter(status=UserStatus.PENDING_APPROVAL).select_related(
        "dealer"
    )
    list_filter = ListFilter(
        request,
        search_fields=("email", "first_name", "last_name", "dealer__name"),
        date_field="date_joined",
        ordering_map={
            "email": "email",
            "name": "first_name",
            "dealer": "dealer__name",
            "date": "date_joined",
        },
        default_ordering="date_joined",
    )
    queryset = list_filter.apply(queryset)
    context = {"users": queryset, **list_filter.as_context()}
    return render(request, "accounts/pending_users.html", context)


@role_required(Role.ADMIN)
@require_POST
def approve_user(request, pk):
    user = get_object_or_404(User, pk=pk, status=UserStatus.PENDING_APPROVAL)
    user.status = UserStatus.APPROVED
    user.approved_by = request.user
    user.approved_at = timezone.now()
    user.save(update_fields=["status", "approved_by", "approved_at"])
    notify.user_approved(user)
    messages.success(request, _("User approved: %(user)s") % {"user": user})
    return redirect("accounts:pending_users")


@role_required(Role.ADMIN)
def reject_user(request, pk):
    user = get_object_or_404(User, pk=pk, status=UserStatus.PENDING_APPROVAL)
    form = RejectUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.status = UserStatus.REJECTED
        user.rejection_reason = form.cleaned_data["reason"]
        user.is_active = False
        user.save(update_fields=["status", "rejection_reason", "is_active"])
        messages.warning(request, _("User rejected: %(user)s") % {"user": user})
        return redirect("accounts:pending_users")
    return render(request, "accounts/reject_user.html", {"form": form, "object": user})


@role_required(Role.ADMIN)
def user_list(request):
    queryset = User.objects.select_related("dealer")
    role = request.GET.get("role") or ""
    status = request.GET.get("status") or ""
    if role:
        queryset = queryset.filter(role=role)
    if status:
        queryset = queryset.filter(status=status)
    list_filter = ListFilter(
        request,
        search_fields=("email", "first_name", "last_name", "dealer__name"),
        date_field="date_joined",
        ordering_map={
            "email": "email",
            "name": "first_name",
            "role": "role",
            "dealer": "dealer__name",
            "date": "date_joined",
        },
        default_ordering="first_name",
    )
    queryset = list_filter.apply(queryset)
    if request.GET.get("export") == "excel":
        return excel_response(
            "users",
            str(_("Users")),
            [
                _("First name"), _("Last name"), _("Email"), _("Role"), _("Dealer"),
                _("Status"), _("Phone"), _("Registered at"),
            ],
            [
                (
                    user.first_name, user.last_name, user.email,
                    user.get_role_display(), user.dealer.name if user.dealer else "",
                    user.get_status_display(), user.phone, user.date_joined,
                )
                for user in queryset
            ],
        )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/user_list.html",
        {
            "page_obj": page,
            "users": page.object_list,
            "roles": Role.choices,
            "statuses": UserStatus.choices,
            "selected_role": role,
            "selected_status": status,
            **list_filter.as_context(),
        },
    )


@role_required(Role.ADMIN)
def user_form(request, pk=None):
    instance = get_object_or_404(User, pk=pk) if pk else None
    form = UserAdminForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, _("User saved: %(user)s") % {"user": user})
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "object": instance})
