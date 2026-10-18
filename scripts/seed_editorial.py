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

NOTES={
"The Internet Was Built For Human Agency. AI Agents Are Changing the Rules.":{
"argument":"The authors argue that internet governance built around human users is challenged when AI agents increasingly act on people's behalf. Their concern is not simply model performance: it is the relationship between agents, accountability and the ability of people to direct actions taken for them.",
"design_relevance":"For an attention assistant, permissions could be scoped to specific tasks and easy to revoke. A person should be able to distinguish a suggestion from an action the system has already taken, inspect delegated decisions and reverse them where possible.",
"caveat":"A policy argument about human agency, not an experiment measuring attention or the efficacy of focus tools."},
"When an AI Agent Says 'I Agree,' Who's Consenting?":{
"argument":"The essay examines who meaningfully consents when an automated agent makes choices or accepts terms on behalf of an individual. Convenience can obscure the point at which a user's intention becomes the system's independent action.",
"design_relevance":"A prospective focus tool could require explicit approval for consequential interventions, including blocking communications or adapting what the user sees, and offer a reviewable record of the user's preferences.",
"caveat":"A normative and legal design issue; its relevance to attention-supporting products is a design inference, not the article's tested finding."},
"New Perspectives on AI Agentiality and Democracy: 'Whom Does It Serve?'":{
"argument":"The authors discuss AI systems that serve people as independent intermediaries, rather than relying exclusively on platform-directed interfaces. Among their proposals are attention guardians that might give individuals more control over feeds and recommendations.",
"design_relevance":"A user-controlled attention guardian could let people specify what they want to attend to and which interruption categories matter, instead of optimizing for time-on-platform. Such a system should preserve user agency and expose its filtering rules.",
"caveat":"This is a concept and governance proposal. It does not demonstrate that attention guardians improve focus or wellbeing."},
"How AI-Powered Emotional Surveillance Can Threaten Personal Autonomy and Democracy":{
"argument":"The author examines how technologies that claim to detect emotions or attention can enable institutional surveillance. Examples in education raise questions about whether machine classifications of mental states are justified or can become coercive.",
"design_relevance":"A future focus app should favor self-reported goals and voluntary reflection over inferred or mandatory attention scores. Research should consider false inferences, surveillance pressure and the possibility that monitoring itself creates distraction.",
"caveat":"A critical policy perspective, not an assessment of a particular focus intervention's effectiveness."}
}

def main():
 path=DIR/"library.json";records=json.loads(path.read_text())
 ids={re.sub(r"\W+","",(r.get("title") or "").lower()) for r in records}
 new=[]
 for r in SOURCES:
  k=re.sub(r"\W+","",r["title"].lower())
  if k in ids:
   for item in records:
    if re.sub(r"\W+","",item.get("title","").lower())==k:
     item["editorial_notes"]=NOTES.get(r["title"],{})
     break
   continue
  ids.add(k)
  overview=r.pop("overview")
  row=dict(r,doi="",kind="nonacademic",editorial_notes=NOTES.get(r["title"],{}),source="Editorially selected public commentary",curated=True,
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
