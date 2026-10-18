"""Small transparent product/documentation landscape for attention-app design."""
import json,pathlib,re,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json";WEEK=ROOT/"data/weekly.json"
TODAY=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
PRODUCTS=[
 {"title":"Intention Tracking [iOS] — one sec","url":"https://feedback.one-sec.app/en/help/articles/5677947-intention-tracking-ios","venue":"one sec","overview":"The one sec app can prompt people to state why they are opening a distracting app. This introduces a moment of reflection at the point of a potentially automatic habit.","argument":"Product documentation describes an intention picker before access to an app. The tool asks people to clarify their reason for opening it.","design_relevance":"Compare deliberate friction against hard blocking and passive tracking. Measure subsequent app-opening decisions, sense of autonomy, and irritation from extra prompts."},
 {"title":"Freedom — App and Website Blocking","url":"https://freedom.to/","venue":"Freedom","overview":"Freedom offers sessions in which selected websites or apps can be blocked across devices. The intervention operates through restricting access to distractions rather than measuring attention continuously.","argument":"Freedom's published feature information describes configurable app and website blocking for planned work periods.","design_relevance":"Compare restriction against softer attention reminders. Consider reversibility, exceptions for urgent communications, and whether users would prefer graduated friction."},
 {"title":"Focus Filters — Apple Developer Documentation","url":"https://developer.apple.com/documentation/appintents/focus/","venue":"Apple Developer","overview":"Apple's Focus APIs allow apps to adapt their behavior or notification handling to an active Focus state. These affordances are relevant to the technical feasibility of a privacy-conscious attention app.","argument":"Apple documents mechanisms through which apps respond to system Focus configurations and filter notifications.","design_relevance":"A prototype could coordinate with system-selected focus states rather than inferring users' mental states or monitoring all applications."},
 {"title":"Android Focus Mode and Digital Wellbeing","url":"https://www.android.com/productivity/","venue":"Android","overview":"Android describes system-level features for pausing distracting apps, managing screen time and notification habits, and configuring focused periods.","argument":"Android presents Focus Mode and Digital Wellbeing controls as user-directed tools for reducing digital interruptions.","design_relevance":"Use the platform's existing pause, schedule, and limit features as a baseline when testing whether a proposed attention tool adds value."}
]
def main():
 records=json.loads(LIB.read_text());ids={re.sub(r"\W+","",(x.get("title") or "").lower()) for x in records}
 new=[]
 for p in PRODUCTS:
  k=re.sub(r"\W+","",p["title"].lower())
  if k in ids:continue
  ids.add(k)
  n={k:p[k] for k in ("argument","design_relevance")}
  n["caveat"]="Product documentation is a description of features, not independently established evidence of effectiveness."
  row={"title":p["title"],"url":p["url"],"venue":p["venue"],"published":"","authors":[],"doi":"","kind":"nonacademic",
       "lane":"Interventions","format":"Product & design","source":"Official product documentation","curated":True,
       "first_seen":TODAY,"evidence":"Product documentation; no independent effectiveness assessment",
       "relation":"Practical design reference","preview":p["overview"],"editorial_notes":n,
       "content_access":"editorial_synopsis",
       "reading":{"level":"curated","provenance":p["venue"]+" published product documentation","overview":p["overview"],"methods":"","findings":"","limitations":"","sample":"",
                  "notice":"Original synopsis of product features. This is not a tested intervention or a claim about its effectiveness."}}
  new.append(row)
 records.extend(new)
 records.sort(key=lambda r:(r.get("published") or "",r.get("first_seen") or ""),reverse=True)
 LIB.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n")
 week=json.loads(WEEK.read_text());week["items"]=new+[x for x in week.get("items",[]) if x.get("title") not in {r["title"] for r in new}][:38]
 week["run"]["new"]=week["run"].get("new",0)+len(new);week["run"]["total"]=len(records)
 week["run"]["product_examples"]=sum(x.get("source")=="Official product documentation" for x in records)
 week["run"]["nonacademic_total"]=sum(x.get("kind")=="nonacademic" for x in records)
 WEEK.write_text(json.dumps(week,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"new_product_design_sources":len(new),"product_references":week["run"]["product_examples"]}))
if __name__=="__main__":main()
