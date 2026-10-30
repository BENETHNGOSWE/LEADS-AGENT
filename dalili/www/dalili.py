import frappe

no_cache = 1


def get_context(context):
    """Gate the portal page behind login and hand the template a CSRF token.

    Nothing here is public: a lead database is personal data under Tanzania's PDPA
    and must never be reachable by a guest session.
    """
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/dalili"
        raise frappe.Redirect

    settings = frappe.get_cached_doc("Dalili Settings")
    if not settings.enable_portal:
        frappe.throw("The Dalili portal page is disabled in Dalili Settings.")

    context.no_cache = 1
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.demo_mode = bool(settings.demo_mode)
    context.site_name = frappe.local.site
    context.region = settings.default_region or "Dar es Salaam"
    return context
