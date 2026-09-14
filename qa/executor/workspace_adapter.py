"""Compile History, Usage, retry and role evidence into Registry results."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceEvidence:
    technical_complete: bool; external_requests: int; console_errors: int; cleanup_total: int
    history_filters: bool; history_offset_zero: bool; history_pages: bool; history_identity: bool
    history_delete_calls: int; history_count_policy: bool
    usage_plan: bool; usage_balance: bool; usage_charges: bool; usage_held: int
    usage_status: int; usage_reload: bool
    retry_original_clean: bool; retry_error_readable: bool; retry_distinct: bool
    retry_link: bool; retry_path: tuple[str, ...]; retry_charge_once: bool
    user_nav_hidden: bool; user_ops_status: int; user_master_status: int; user_admin_polls: int
    master_nav: bool; master_overview: bool; master_users: bool; master_audit: bool; master_ops: bool

def _a(i:str,p:bool,e:list[str])->dict[str,Any]:return{"id":i,"passed":p,"evidence":e}
def _r(i:str,a:list[dict[str,Any]])->dict[str,Any]:return{"scenario_id":i,"selected":True,"verdict":"FAIL"if any(not x["passed"]for x in a)else"PASS","assertions":a,"blocked_reasons":[]}

def compile_workspace_results(e:WorkspaceEvidence)->tuple[dict[str,Any],...]:
    if not(e.technical_complete and e.external_requests==0 and e.console_errors==0 and e.cleanup_total==0):
        return tuple({"scenario_id":i,"selected":True,"verdict":"BLOCKED","assertions":[],"blocked_reasons":["workspace_evidence_incomplete"]}for i in("history_navigation","usage_credits","failure_retry","role_ops_master"))
    history=[_a("history.filters_match_rows",e.history_filters,["ui_snapshot","network"]),_a("history.filter_resets_offset",e.history_offset_zero,["network"]),_a("history.page_controls_match_count",e.history_pages,["ui_snapshot","network"]),_a("history.detail_preserves_job_identity",e.history_identity,["url","network"]),_a("history.cancel_delete_has_zero_deletes",e.history_delete_calls==0,["network","runtime_receipt"]),_a("history.visible_count_matches_policy",e.history_count_policy,["ui_snapshot"])]
    usage=[_a("usage.plan_visible",e.usage_plan,["ui_snapshot"]),_a("usage.balance_matches_ledger",e.usage_balance,["usage_read_model","database"]),_a("usage.job_charges_match_ledger",e.usage_charges,["usage_read_model","database"]),_a("usage.held_is_zero_after_terminal",e.usage_held==0,["usage_read_model"]),_a("usage.reload_fetches_current_state",e.usage_status==200,["network","usage_read_model"]),_a("usage.values_survive_reload",e.usage_reload,["ui_snapshot","usage_read_model"])]
    retry=[_a("retry.original_failed_without_asset",e.retry_original_clean,["database"]),_a("retry.error_is_user_readable",e.retry_error_readable,["ui_snapshot"]),_a("retry.creates_distinct_job",e.retry_distinct,["database","network"]),_a("retry.link_preserves_origin",e.retry_link,["database"]),_a("retry.new_job_completed",e.retry_path==("pending","running","completed"),["database","runtime_receipt"]),_a("retry.no_duplicate_charge",e.retry_charge_once,["usage_read_model","database"])]
    role=[_a("role.user_admin_navigation_hidden",e.user_nav_hidden,["ui_snapshot"]),_a("role.user_ops_access_refused",e.user_ops_status==403,["network","access_log"]),_a("role.user_master_access_refused",e.user_master_status==403,["network","access_log"]),_a("role.user_has_zero_admin_polling",e.user_admin_polls==0,["network"]),_a("role.master_navigation_visible",e.master_nav,["ui_snapshot"]),_a("role.master_overview_visible",e.master_overview,["ui_snapshot","network"]),_a("role.master_users_visible",e.master_users,["ui_snapshot","network"]),_a("role.master_audit_visible",e.master_audit,["ui_snapshot","network"]),_a("role.master_ops_visible",e.master_ops,["ui_snapshot","network"])]
    return _r("history_navigation",history),_r("usage_credits",usage),_r("failure_retry",retry),_r("role_ops_master",role)
