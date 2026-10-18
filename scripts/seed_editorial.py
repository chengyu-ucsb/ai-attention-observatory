"""A short, transparent editorial selection of public essays relevant to attention/app design.

Summaries are authored here; NOT quotations or a claim of systematic full-text review.
The normal RSS collector still discovers newer material each week.
"""
import json,datetime,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1];DIR=ROOT/"data"
TODAY=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
SOURCES=[
 dict(title="The Internet Was Built For Human Agency. AI Agents Are Changing the Rules.",url="https://www.techpolicy.press/the-internet-was-built-for-human-agency-ai-agents-are-changing-the-rules/",venue="Tech Policy Press",published="2026-09-10",authors=["Konstantinos Komaitis","Rumman Chowdhury"],lane="Technology & society",format="Policy analysis",overview="This essay argues that AI agents change the architecture of participation online because software increasingly acts on a person's behalf. For attention-supporting tools, it raises a design question about agency: who chooses what is delegated, and who can inspect or reverse the choices?"),
 dict(title="When an AI Agent Says 'I Agree,' Who's Consenting?",url="https://www.techpolicy.press/when-an-ai-agent-says-i-agree-whos-consenting/",venue="Tech Policy Press",published="2025-12-12",authors=["Camillia Rida"],lane="Technology & society",format="Opinion & analysis",overview="The author considers how agentic convenience complicates consent as systems make decisions on a user's behalf. The argument is useful for developing focus assistants that negotiate permissions clearly instead of quietly taking control of user choices."),
 dict(title="New Perspectives on AI Agentiality and Democracy: 'Whom Does It Serve?'",url="https://www.techpolicy.press/new-perspectives-on-ai-agentiality-and-democracy-whom-does-it-serve/",venue="Tech Policy Press",published="2024-12-06",authors=["Richard Reisman","Richard Whitt"],lane="Interventions",format="Product & design",overview="This analysis proposes user-controlled AI intermediaries, including attention guardians, as an alternative to platform-directed information flows. It offers a potential design direction for an attention app, but should be read as a proposal rather than evidence that such an intervention works."),
 dict(title="How AI-Powered Emotional Surveillance Can Threaten Personal Autonomy and Democracy",url="https://www.techpolicy.press/how-ai-powered-emotional-surveillance-can-threaten-personal-autonomy-and-democracy/",venue="Tech Policy Press",published="2025-10-07",authors=["Oznur Uguz"],lane="Technology & society",format="Policy analysis",overview="The piece considers the autonomy risks of AI-based emotion and attention surveillance, including technologies used in educational settings. For the Experimental Lab, it highlights why a focus app should avoid treating attention monitoring as an objective measure of what a person ought to do.")
]
def main():
 path=DIR/"library.json";records=json.loads(path.read_text())
 ids={re.sub(r"\W+","",(r.get("title") or "").lower()) for r in records}
 new=[]
 for r in SOURCES:
  k=re.sub(r"\W+","",r["title"].lower())
  if k in ids:continue
  ids.add(k)
  overview=r.pop("overview")
  row=dict(r,doi="",kind="nonacademic",source="Editorially selected public commentary",curated=True,
    first_seen=TODAY,evidence="Source-grounded editorial synopsis; not a peer-reviewed study",
    relation="Commentary / design perspective",preview=overview,
    content_access="editorial_synopsis",
    reading=dict(level="curated",provenance=r["venue"]+" public essay (editorially summarized)",
                 overview=overview,methods="",findings="",limitations="",sample="",
                 notice="An original editorial synopsis of this essay's argument, not a verified empirical finding or complete review."))
  new.append(row)
 records.extend(new);records.sort(key=lambda r:(r.get("published") or "",r.get("first_seen") or ""),reverse=True)
 path.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n")
 weekpath=DIR/"weekly.json";week=json.loads(weekpath.read_text());items=week.get("items",[])
 # Keep the editorial channel visible without displacing the three featured scholarly readings.
 week["items"]=new[:4]+[it for it in items if it.get("title") not in {x["title"] for x in new}][:36]
 week["run"]["total"]=len(records)
 week["run"]["new"]=week["run"].get("new",0)+len(new)
 week["run"]["nonacademic_total"]=sum(x.get("kind")=="nonacademic" for x in records)
 week["run"]["editorial_selections_added"]=len(new)
 weekpath.write_text(json.dumps(week,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"editorially_selected_added":len(new),"total_library":len(records)}))
if __name__=="__main__":main()
