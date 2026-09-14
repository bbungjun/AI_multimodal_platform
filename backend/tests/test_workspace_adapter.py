from dataclasses import replace
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"qa"/"executor"))
from workspace_adapter import WorkspaceEvidence,compile_workspace_results  # noqa:E402

def evidence():return WorkspaceEvidence(True,0,0,0,True,True,True,True,0,True,True,True,True,0,200,True,True,True,True,True,("pending","running","completed"),True,True,403,403,0,True,True,True,True,True)
def test_complete_workspace_evidence_passes_27_assertions():
 r=compile_workspace_results(evidence());assert[len(x["assertions"])for x in r]==[6,6,6,9];assert all(x["verdict"]=="PASS"for x in r)
def test_user_ops_navigation_mismatch_is_role_fail():
 r=compile_workspace_results(replace(evidence(),user_nav_hidden=False,user_admin_polls=2));assert r[3]["verdict"]=="FAIL";assert len([x for x in r[3]["assertions"]if not x["passed"]])==2
def test_cleanup_or_tool_gap_blocks_all():
 r=compile_workspace_results(replace(evidence(),cleanup_total=1));assert all(x["verdict"]=="BLOCKED"and not x["assertions"]for x in r)
def test_retry_state_path_is_strict():
 r=compile_workspace_results(replace(evidence(),retry_path=("pending","completed")));assert r[2]["verdict"]=="FAIL"
