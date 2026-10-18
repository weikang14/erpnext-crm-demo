from django.contrib.auth.views import LogoutView
from django.urls import path

from sales.views import accounts, activities, auth, enquiry, home, leads, opportunities, quotes, reports

urlpatterns = [
    path("", home.my_day, name="home"),
    path("login/", auth.RateLimitedLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("enquiry/", enquiry.enquiry, name="enquiry"),
    path("enquiry/thanks/", enquiry.thanks, name="enquiry_thanks"),
    # leads
    path("leads/", leads.lead_list, name="leads"),
    path("leads/new/", leads.lead_new, name="lead_new"),
    path("leads/<int:pk>/", leads.lead_detail, name="lead"),
    path("leads/<int:pk>/convert/", leads.lead_convert, name="lead_convert"),
    path("leads/<int:pk>/disqualify/", leads.lead_disqualify, name="lead_disqualify"),
    path("leads/<int:pk>/assign/", leads.lead_assign, name="lead_assign"),
    path("leads/<int:pk>/edit/", leads.lead_edit, name="lead_edit"),
    # accounts
    path("accounts/", accounts.account_list, name="accounts"),
    path("accounts/new/", accounts.account_new, name="account_new"),
    path("accounts/<int:pk>/", accounts.account_detail, name="account"),
    path("accounts/<int:pk>/edit/", accounts.account_edit, name="account_edit"),
    path("accounts/<int:pk>/contacts/", accounts.contact_add, name="account_contact_add"),
    path("accounts/<int:pk>/contacts/<int:contact>/edit/", accounts.contact_edit, name="account_contact_edit"),
    path("accounts/<int:pk>/deals/", accounts.deal_new, name="account_deal_new"),
    # activities
    path("activities/<str:parent>/<int:pk>/", activities.activity_add, name="activity_add"),
    path("activities/<int:pk>/done/", activities.activity_done, name="activity_done"),
    # deals
    path("pipeline/", opportunities.pipeline, name="pipeline"),
    path("deals/", opportunities.deal_list, name="opportunities"),
    path("deals/<int:pk>/", opportunities.deal_detail, name="opportunity"),
    path("deals/<int:pk>/move/", opportunities.deal_move, name="opportunity_move"),
    path("deals/<int:pk>/won/", opportunities.deal_won, name="opportunity_won"),
    path("deals/<int:pk>/lost/", opportunities.deal_lost, name="opportunity_lost"),
    path("deals/<int:pk>/edit/", opportunities.deal_edit, name="opportunity_edit"),
    path("deals/<int:pk>/assign/", opportunities.deal_assign, name="opportunity_assign"),
    path("deals/<int:pk>/erp/send/", opportunities.deal_erp_send, name="opportunity_erp_send"),
    path("deals/<int:pk>/quotes/", quotes.quote_new, name="opportunity_quote_new"),
    # quotes
    path("quotes/<int:pk>/", quotes.quote_detail, name="quote"),
    path("quotes/<int:pk>/lines/", quotes.line_add, name="quote_line_add"),
    path("quotes/<int:pk>/lines/<int:line>/delete/", quotes.line_delete, name="quote_line_delete"),
    path("quotes/<int:pk>/print/", quotes.quote_print, name="quote_print"),
    path("quotes/<int:pk>/<str:action>/", quotes.quote_action, name="quote_action"),  # submit, approve, reject, send, revise
    path("approvals/", quotes.approvals, name="approvals"),
    # reports
    path("reports/", reports.report_page, name="reports"),
]
