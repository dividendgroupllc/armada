app_name = "armada"
app_title = "Armada Custom app"
app_publisher = "Sardorbek"
app_description = "Armada uchun app"
app_email = "sardorbekqamchibekov76@gmail.com"
app_license = "mit"

# Fixtures
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ("Stock Entry", "Item", "Kassa", "Sales Invoice")],
            [
                "fieldname", "in", (
                    "custom_production_entry",
                    "armada_category_section",
                    "fp_type",
                    "segment",
                    "product_type",
                    "standard",
                    "custom_no_bom_required",
                    "custom_barcode",
                    "custom_sub_account_name",
                    "custom_auto_created_from_sales_order",
                )
            ]
        ]
    },
    {
        "dt": "Custom Field",
        "filters": [
            ["name", "in", [
                "Customer-telegram_chat_id",
                "Customer-telegram_invite_token",
                "Supplier-telegram_chat_id",
                "Supplier-telegram_invite_token",
            ]]
        ]
    },
    "Account Name Mapping",
    "Account Name Mapping Item"
]
# Apps
# ------------------
doc_events = {
    "Item": {
        "before_insert": "armada.armada_custom_app.barcode.ensure_item_barcode",
        "validate": "armada.armada_custom_app.barcode.sync_item_barcode_display",
    },
    "Sales Order": {
        "on_submit": "armada.armada_custom_app.events.sales_order.on_sales_order_submit",
        "before_cancel": "armada.armada_custom_app.events.sales_order.before_sales_order_cancel",
    },
    "Cash Flow Categories": {
        "on_update": "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.clear_cache",
        "on_trash":  "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.clear_cache",
    },
    # ── Telegram bildirişnomalari ──────────────────────────────────────────────
    "Sales Invoice": {
        "on_submit": "armada.armada_custom_app.events.sales_invoice.on_submit",
    },
    "Purchase Invoice": {
        "on_submit": "armada.armada_custom_app.events.purchase_invoice.on_submit",
    },
    "Payment Entry": {
        "on_submit": "armada.armada_custom_app.events.payment_entry.on_submit",
        "on_cancel": "armada.armada_custom_app.events.payment_entry.on_cancel",
    },
}
# required_apps = []

add_to_apps_screen = [
	{
		"name": "armada",
		"logo": "/assets/armada/images/armada-logo.png",
		"title": "Armada Dashboard",
		"route": "/app/armada-dashboard",
	}
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "armada",
# 		"logo": "/assets/armada/logo.png",
# 		"title": "Armada Custom app",
# 		"route": "/armada",
# 		"has_permission": "armada.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

app_include_css = "/assets/armada/css/armada-dashboard.css"
app_include_js = [
	"https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
	"/assets/armada/js/armada-dashboard.bundle.js",
	"/assets/armada/js/report_formatter.js",
	"/assets/armada/js/pl_pdf_button.js",
	"/assets/armada/js/balance_sheet_pdf.js",
	"/assets/armada/js/report_overrides.js",
	"/assets/armada/js/cash_flow_formatter.js",
]

# include js, css files in header of desk.html
# app_include_css = "/assets/armada/css/armada.css"
# app_include_js = "/assets/armada/js/armada.js"

# include js, css files in header of web template
# web_include_css = "/assets/armada/css/armada.css"
# web_include_js = "/assets/armada/js/armada.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "armada/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Journal Entry": "public/js/journal_entry.js",
	"Sales Invoice": "public/js/item_code_barcode_scan.js",
	"Delivery Note": "public/js/item_code_barcode_scan.js",
	"Stock Entry": "public/js/item_code_barcode_scan.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "armada/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "armada.utils.jinja_methods",
# 	"filters": "armada.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "armada.install.before_install"
# after_install = "armada.install.after_install"

# Migration
# ---------
# "Gross Profit" reportida dublikat total qatori chiqmasligi uchun
# add_total_row=0 ni har migratsiyada enforce qilamiz.
after_migrate = ["armada.overrides.gross_profit.ensure_no_duplicate_total"]

# Uninstallation
# ------------

# before_uninstall = "armada.uninstall.before_uninstall"
# after_uninstall = "armada.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "armada.utils.before_app_install"
# after_app_install = "armada.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "armada.utils.before_app_uninstall"
# after_app_uninstall = "armada.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "armada.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"*/3 * * * *": [
			"armada.armada_custom_app.api.counterparties.refresh_counterparty_cache"
		]
	}
}

# scheduler_events = {
# 	"all": [
# 		"armada.tasks.all"
# 	],
# 	"daily": [
# 		"armada.tasks.daily"
# 	],
# 	"hourly": [
# 		"armada.tasks.hourly"
# 	],
# 	"weekly": [
# 		"armada.tasks.weekly"
# 	],
# 	"monthly": [
# 		"armada.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "armada.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "armada.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "armada.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["armada.utils.before_request"]
# after_request = ["armada.utils.after_request"]

# Job Events
# ----------
# before_job = ["armada.utils.before_job"]
# after_job = ["armada.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"armada.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
