from dataclasses import replace
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"qa"/"executor"))
from workspace_adapter import WorkspaceEvidence,compile_workspace_results,evidence_from_workspace_receipt  # noqa:E402

def evidence():return WorkspaceEvidence(True,0,0,0,True,True,True,True,0,True,True,True,True,0,200,True,True,True,True,True,("pending","running","completed"),True,True,403,403,0,True,True,True,True,True)
def test_complete_workspace_evidence_passes_27_assertions():
 r=compile_workspace_results(evidence());assert[len(x["assertions"])for x in r]==[6,6,6,9];assert all(x["verdict"]=="PASS"for x in r)
def test_user_ops_navigation_mismatch_is_role_fail():
 r=compile_workspace_results(replace(evidence(),user_nav_hidden=False,user_admin_polls=2));assert r[3]["verdict"]=="FAIL";assert len([x for x in r[3]["assertions"]if not x["passed"]])==2
def test_cleanup_or_tool_gap_blocks_all():
 r=compile_workspace_results(replace(evidence(),cleanup_total=1));assert all(x["verdict"]=="BLOCKED"and not x["assertions"]for x in r)
def test_retry_state_path_is_strict():
 r=compile_workspace_results(replace(evidence(),retry_path=("pending","completed")));assert r[2]["verdict"]=="FAIL"
def test_receipt_compiler_keeps_master_503_as_product_fail():
 r={"driver_exit_code":0,"master_driver_exit_code":0,"runtime_cleanup":0,"source_unchanged":True,
  "browser":{"cleanup":0,"external_page_requests":0,"unexpected_console_errors":0,"workspace":{"technical_complete":True,
   "phases":{"filtered":True,"page2":True,"page1":True,"usage":True,"usage_reloaded":True},"history_offsets":[0,0,20,0],
   "history_visible_count":20,"history_rows":20,"detail_identity":True,"delete_calls":0,"retry_error_readable":True,
   "usage_statuses":[200,200],"usage_values":{"before":{"available":"999.9","held":"0","charged":"0.1"},"after":{"available":"999.9","held":"0","charged":"0.1"}},
   "ops_statuses":[403],"master_statuses":[403],"user_admin_polls":0,"user_ops_nav_visible":False}},
  "master_browser":{"cleanup":0,"external_page_requests":0,"unexpected_console_errors":0,"master":{"technical_complete":True,
   "phases":{"navigation":True,"overview":True,"users":True,"audit":True,"ops":True},"statuses":{"overview":[200],"users":[503],"audit":[200],"ops":[200]}}},
  "workspace_inspect":{"usage_available":999900000,"usage_held":0,"usage_charged":100000,"usage_meter_charged":100000,"usage_plan":"free",
   "original_failed_clean":True,"original_error_present":True,"retry_distinct":True,"retry_link":True,"retry_state_path":"pending,running,completed","retry_charge_once":True}}
 result=compile_workspace_results(evidence_from_workspace_receipt(r));assert result[3]["verdict"]=="FAIL";assert result[0]["verdict"]=="PASS"
