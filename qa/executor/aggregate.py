"""Run and aggregate all ten Agent QA scenarios into one contract Receipt."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any,Callable
from uuid import uuid4

from prompt_t2i_adapter import PromptT2IProbes,compile_prompt_t2i_results,sanitize_image_journey_report
from runner import ExecutorError,build_selection,current_revision,run_execution,source_digest
from video_pipeline_adapter import VideoPipelineEvidence,compile_video_pipeline_results
from workspace_adapter import compile_workspace_results,evidence_from_workspace_receipt


RUN_ID=re.compile(r"^agent-qa-aggregate-[0-9a-f]{12}$")
SLICE=re.compile(r"^output[\\/]playwright[\\/]devtools-(?:image|video|i2v|pipeline|workspace)-[0-9a-f]{12}[\\/]receipt\.json$")


@dataclass(frozen=True)
class AggregateRun:
    receipt:dict[str,Any]
    report_path:str
    merge_decision:str
    seconds:float


def _slice(command:list[str],root:Path,run:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    result=run(command,cwd=root,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=900,check=False)
    try:
        summary=json.loads(next(line for line in reversed(result.stdout.splitlines())if line.startswith("{")))
        relative=summary["receipt"]
        if type(relative)is not str or not SLICE.fullmatch(relative):raise ValueError
        path=(root/relative).resolve();allowed=(root/"output"/"playwright").resolve()
        if allowed not in path.parents:raise ValueError
        value=json.loads(path.read_text(encoding="utf-8"))
    except(OSError,ValueError,KeyError,StopIteration,TypeError,json.JSONDecodeError):
        raise ExecutorError("aggregate_slice_invalid")from None
    if(result.returncode not in{0,1}or type(value)is not dict or value.get("provider")!="mock"or"error"in value or value.get("runtime_cleanup")!=0
       or value.get("source_unchanged")is not True or value.get("driver_exit_code")!=0):
        raise ExecutorError("aggregate_slice_incomplete")
    return value


def _prompt_results(r:dict[str,Any])->tuple[dict[str,Any],...]:
    try:
        image=r["browser"]["image"];delta=r["prompt_t2i_probe"]["refusal_deltas"]
        probes=PromptT2IProbes(image["checks"]["discarded"],image["checks"]["empty_dom_disabled"],
            image["over_limit_status"],delta["jobs"],delta["outbox"],delta["reservations"],tuple(r["prompt_t2i_job_probe"]["state_path"].split(",")))
        clean=sanitize_image_journey_report(r["browser"])
        ready=r["runtime_cleanup"]==0 and r["source_unchanged"]is True and r["driver_exit_code"]==0
        return compile_prompt_t2i_results(clean,probes,runtime_receipt_ready=ready)
    except(KeyError,TypeError,ValueError):raise ExecutorError("aggregate_prompt_invalid")from None


def _video_results(t:dict[str,Any],i:dict[str,Any],p:dict[str,Any])->tuple[dict[str,Any],...]:
    try:
        reports=(t,i,p);tv=t["browser"]["video"];iv=i["browser"]["i2v"];pv=p["browser"]["pipeline"]
        tp=t["video_job_probe"];ip=i["i2v_job_probe"];pp=p["pipeline_probe"]
        ready=all(r["driver_exit_code"]==0 and r["runtime_cleanup"]==0 and r["source_unchanged"]is True
            and r["browser"]["cleanup"]==0 for r in reports)and tv["technical_complete"]is True and iv["technical_complete"]is True and pv["technical_complete"]is True
        e=VideoPipelineEvidence(ready,sum(r["browser"]["external_page_requests"]for r in reports),
            sum(r["browser"]["unexpected_console_errors"]for r in reports),sum(r["browser"]["cleanup"]+r["runtime_cleanup"]for r in reports),
            tv["product"]["empty_disabled"]and tv["empty_accessibility_disabled"],tv["over_limit_status"],
            sum(t["video_probe"]["refusal_deltas"].values()),tuple(tp["state_path"].split(",")),tp["asset_mime"],tv["product"]["outcome_usable"],
            iv["no_source_accessibility_disabled"],iv["source_matches"],ip["source_present"],tuple(ip["state_path"].split(",")),ip["asset_mime"],iv["usable"],
            pv["phases"]["incomplete"]and pv["incomplete_accessibility_disabled"],pp["same_owner"],tuple(pp["child_path"].split(",")),pp["source_linked"],
            pp["parent_state"],pp["child_state"],pp["reservations"],pp["held"],pv["phases"]["reloaded"])
        return compile_video_pipeline_results(e)
    except(KeyError,TypeError,ValueError):raise ExecutorError("aggregate_video_invalid")from None


def aggregate_reports(*,revision:str,registry:Any,auth:dict[str,Any],image:dict[str,Any],video:dict[str,Any],
                      i2v:dict[str,Any],pipeline:dict[str,Any],workspace:dict[str,Any])->dict[str,Any]:
    slices=(image,video,i2v,pipeline,workspace)
    if(auth.get("revision")!=revision or any(row.get("revision")!=revision for row in slices)):
        raise ExecutorError("aggregate_revision_stale")
    if(not auth.get("source_unchanged")or any(row.get("source_unchanged")is not True for row in slices)):
        raise ExecutorError("aggregate_source_changed")
    results=(auth["scenario_result"],*_prompt_results(image),*_video_results(video,i2v,pipeline),
             *compile_workspace_results(evidence_from_workspace_receipt(workspace)))
    indexed={row["scenario_id"]:row for row in results}
    if(set(indexed)!=set(registry.by_id())):raise ExecutorError("aggregate_scenario_coverage_invalid")
    ordered=[indexed[row["id"]]for row in registry.scenarios]
    cleanup={"browser":auth["cleanup"]["browser"]+sum(row["browser"]["cleanup"]!=0 for row in slices),
             "mcp":auth["cleanup"]["mcp"],"vite":auth["cleanup"]["vite"],
             "runtime":auth["cleanup"]["runtime"]+sum(row["runtime_cleanup"]for row in slices)}
    verdict="FAIL"if any(row["verdict"]=="FAIL"for row in ordered)else"BLOCKED"if(any(row["verdict"]=="BLOCKED"for row in ordered)or any(cleanup.values()))else"PASS"
    return{"schema_version":1,"run_id":"agent-qa-aggregate-"+uuid4().hex[:12],"revision":revision,
           "registry_sha256":registry.sha256,"provider":"mock","source_unchanged":True,
           "scenario_results":ordered,"cleanup":cleanup,"verdict":verdict}


def run_all(base_revision:str,head_revision:str,root:Path,*,run:Callable[...,Any]=subprocess.run)->AggregateRun:
    started=time.monotonic();registry,selection=build_selection(base_revision,head_revision,root)
    if selection["classification"]!="FULL_E2E"or not all(row["selected"]for row in selection["scenario_decisions"]):
        raise ExecutorError("aggregate_full_selection_required")
    before=source_digest(root);auth=run_execution(base_revision,head_revision,"auth_login",repository_root=root,process_runner=run)
    slices={name:_slice(["python",str(root/"scripts"/"devtools_login_qa.py"),"--scenario",name,"--auto"],root,run)
            for name in("image","video","i2v","pipeline","workspace")}
    if current_revision(root)!=head_revision or source_digest(root)!=before:raise ExecutorError("aggregate_source_changed")
    receipt=aggregate_reports(revision=head_revision,registry=registry,auth=auth,**slices)
    from registry import validate_receipt
    validate_receipt(receipt,registry,expected_revision=head_revision)
    output=root/"output"/"playwright"/receipt["run_id"];output.mkdir(parents=True,exist_ok=False)
    path=output/"receipt.json";path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    return AggregateRun(receipt,str(path.relative_to(root)),"ALLOW"if receipt["verdict"]=="PASS"else"REJECT",
                        round(time.monotonic()-started,3))
