/// Code shared by the two Flutter clients (`apps/user`, `apps/admin`).
///
/// Only genuinely app-agnostic pieces belong here. Anything that needs to know
/// which app it is running in — the `User` / `Admin` models, the home and
/// payment screens — deliberately stays in each app. The bottom-navigation
/// shell and the cost-detail page were app-specific only in the types they
/// mentioned, so they now live here parameterised ([HomeShell] takes the nav
/// items and pages, [CostDetailPage] takes a builder for the back button).
/// See apps/README.md for what was evaluated and rejected.
library checkout_common;

export 'src/api_client.dart';
export 'src/api_config.dart';
export 'src/auth_session.dart';
export 'src/cost_detail_page.dart';
export 'src/forget_password_page.dart';
export 'src/home_shell.dart';
export 'src/menu_items.dart';
export 'src/month_day_picker.dart';
export 'src/register_page.dart';
