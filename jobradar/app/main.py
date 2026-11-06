"""HTTP application entry point and API for the standalone Jobradar."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .database import connect, database_is_ready, initialize_database

JobStatus = Literal["neu", "gemerkt", "beworben", "absage", "verworfen"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Jobradar",
    version="0.2.0",
    description="Lokaler, KI-unabhängiger Jobradar für Home Assistant",
    lifespan=lifespan,
)


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    company: str | None = None
    location: str | None = None
    url: str | None = None
    source: str | None = None
    description: str | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    remote_type: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    published_at: str | None = None


class JobPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=10000)
    score: int | None = Field(default=None, ge=0, le=100)


class ProfileUpdate(BaseModel):
    data: dict[str, Any]


class RuleUpdate(BaseModel):
    data: dict[str, Any]


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#101827"><title>Jobradar</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#121d2e;--line:#26364d;--text:#edf3fb;--muted:#91a2b8;--accent:#73a7ff;--green:#55d6a1}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 80% -15%,#1c3656 0,transparent 42%),var(--bg);color:var(--text);font:15px/1.5 Inter,system-ui,sans-serif}.shell{max-width:1440px;margin:auto;padding:28px 34px 60px}.top,.welcome,.panel-head,.job,.dialog-head,.actions{display:flex;align-items:center;justify-content:space-between;gap:14px}.brand{display:flex;align-items:center;gap:13px}.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,#76b4ff,#6ce0ba);display:grid;place-items:center;color:#071522;font-size:23px;font-weight:900}.brand h1{font-size:21px;margin:0}.brand p,.welcome p{margin:1px 0 0;color:var(--muted);font-size:12px}.live{border:1px solid #285843;color:var(--green);background:#10291f;padding:7px 12px;border-radius:30px;font-size:12px}.welcome{margin:34px 0 22px;align-items:end}.welcome h2{font-size:clamp(25px,4vw,34px);letter-spacing:-1px;margin:0 0 5px}.welcome p{font-size:14px}.updated,.muted{color:var(--muted);font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:24px}.stat,.panel,.job{background:linear-gradient(145deg,rgba(24,39,59,.96),rgba(17,28,44,.96));border:1px solid var(--line);border-radius:17px}.stat{padding:17px 18px}.stat label{display:block;color:var(--muted);font-size:12px;margin-bottom:7px}.stat strong{font-size:28px}.stat small{display:block;color:var(--muted);font-size:11px}.content{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px}.panel{padding:19px}.panel h3{margin:0;font-size:16px}.filters{display:flex;gap:9px;flex-wrap:wrap;margin:16px 0}input,select,textarea{font:inherit;color:var(--text);background:#0d1726;border:1px solid var(--line);border-radius:10px;padding:10px 12px;outline:none;min-width:0}.filters input{flex:1;min-width:180px}.filters select{min-width:130px}.jobs{display:grid;gap:10px}.job{padding:15px 16px;cursor:pointer}.job:hover{border-color:#5278a7}.job h4{margin:0 0 4px;font-size:15px}.company{color:#c0cee0;font-size:13px}.meta{display:flex;flex-wrap:wrap;gap:7px 13px;margin-top:10px;color:var(--muted);font-size:12px}.score{min-width:53px;text-align:center;padding:7px 9px;border-radius:11px;background:#193653;color:#9dc8ff;font-weight:750}.empty{padding:34px 12px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:13px}.side{display:grid;gap:14px;align-content:start}.side .panel{padding:17px}.status-list{display:grid;gap:11px;margin-top:15px}.status-row{display:flex;justify-content:space-between;color:var(--muted);font-size:13px}.status-row b{color:var(--text)}.runbox{font-size:13px;color:var(--muted);line-height:1.8;margin-top:12px}.runbox strong{color:var(--text)}.detail{position:fixed;inset:0;background:#050a12b8;display:none;align-items:center;justify-content:center;padding:18px;z-index:5}.detail.open{display:flex}.dialog{width:min(620px,100%);max-height:90vh;overflow:auto;background:#132034;border:1px solid #344963;border-radius:18px;padding:22px}.dialog h3{margin:0 0 5px;font-size:21px}.dialog .meta{margin:12px 0 18px}.dialog textarea,.dialog select{width:100%;margin:7px 0 14px}.dialog textarea{min-height:100px;resize:vertical}.dialog label{display:block;color:var(--muted);font-size:12px}.btn{border:1px solid var(--line);background:#1b2c43;color:var(--text);border-radius:10px;padding:9px 12px;cursor:pointer;font-weight:600}.btn.primary{background:#2863a8;border-color:#3679c6}.actions a{color:#9dc8ff;text-decoration:none;font-size:13px}
@media(max-width:900px){.content{grid-template-columns:1fr}.side{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.shell{padding:18px 14px 40px}.welcome{align-items:start;flex-direction:column}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.stat{padding:14px}.stat strong{font-size:24px}.side{grid-template-columns:1fr}.panel{padding:14px}.updated{display:none}}
</style></head><body><main class="shell">
<header class="top"><div class="brand"><div class="logo">⌕</div><div><h1>Jobradar</h1><p>Dein persönlicher IT-Karriere-Kompass</p></div></div><span class="live">● System bereit</span></header>
<section class="welcome"><div><h2>Guten Morgen.</h2><p>Hier ist deine aktuelle Jobübersicht.</p></div><span class="updated" id="updated">Daten werden geladen …</span></section>
<section class="stats"><div class="stat"><label>Alle Stellen</label><strong id="total">–</strong><small>in deiner Jobdatenbank</small></div><div class="stat"><label>Neu</label><strong id="new">–</strong><small>noch nicht bearbeitet</small></div><div class="stat"><label>Gemerkte Stellen</label><strong id="saved">–</strong><small>interessante Möglichkeiten</small></div><div class="stat"><label>Ø Match-Score</label><strong id="average">–</strong><small>über alle bewerteten Stellen</small></div></section>
<section class="content"><div class="panel"><div class="panel-head"><h3>Stellenangebote</h3><span class="muted" id="result-count">0 Treffer</span></div><div class="filters"><input id="search" placeholder="Position, Unternehmen oder Ort suchen …"><select id="status"><option value="">Alle Status</option><option value="neu">Neu</option><option value="gemerkt">Gemerkt</option><option value="beworben">Beworben</option><option value="absage">Absage</option><option value="verworfen">Verworfen</option></select><select id="minimum"><option value="">Alle Scores</option><option value="55">Ab 55 Punkten</option><option value="70">Ab 70 Punkten</option><option value="85">Ab 85 Punkten</option></select></div><div class="jobs" id="jobs"><div class="empty">Stellenangebote werden geladen …</div></div></div>
<aside class="side"><div class="panel"><div class="panel-head"><h3>Statusübersicht</h3></div><div class="status-list" id="status-list"></div></div><div class="panel"><div class="panel-head"><h3>Letzter Suchlauf</h3></div><div class="runbox" id="last-run">Noch keine Suchläufe erfasst.</div></div><div class="panel"><div class="panel-head"><h3>Suchquellen</h3><button class="btn primary" id="add-source">+ Quelle</button></div><div class="status-list" id="sources"><div class="muted">Quellen werden geladen …</div></div></div><div class="panel"><h3>Hinweis</h3><p class="muted">Aktuell werden lokal gespeicherte Stellen angezeigt. Automatische Suche und Quellenadapter folgen in den nächsten Ausbaustufen.</p></div></aside></section></main>
<div class="detail" id="detail"><div class="dialog"><div class="dialog-head"><div><h3 id="detail-title"></h3><div class="company" id="detail-company"></div></div><button class="btn" id="close">✕</button></div><div class="meta" id="detail-meta"></div><label for="detail-status">Status</label><select id="detail-status"><option value="neu">Neu</option><option value="gemerkt">Gemerkt</option><option value="beworben">Beworben</option><option value="absage">Absage</option><option value="verworfen">Verworfen</option></select><label for="detail-notes">Notizen</label><textarea id="detail-notes" placeholder="Deine Notizen zur Stelle …"></textarea><div class="actions"><a id="source-link" target="_blank" rel="noopener">Originalanzeige öffnen ↗</a><button class="btn primary" id="save">Änderungen speichern</button></div></div></div>
<div class="detail" id="source-detail"><div class="dialog"><div class="dialog-head"><div><h3 id="source-heading">Suchquelle</h3><div class="muted">Quelle und Suchbegriffe verwalten</div></div><button class="btn" id="source-close">✕</button></div><form id="source-form"><label for="source-id">Technische ID</label><input id="source-id" required maxlength="100" placeholder="z. B. arbeitsagentur" style="width:100%;margin:7px 0 14px"><label for="source-name">Name</label><input id="source-name" required maxlength="200" style="width:100%;margin:7px 0 14px"><label for="source-type">Quellentyp</label><select id="source-type" style="width:100%;margin:7px 0 14px"><option value="web">Webseite</option><option value="api">API</option><option value="email">E-Mail</option><option value="manual">Manuell</option></select><label for="source-url">Basis-URL</label><input id="source-url" type="url" maxlength="2000" placeholder="https://…" style="width:100%;margin:7px 0 14px"><label for="source-queries">Suchbegriffe (eine Zeile pro Begriff)</label><textarea id="source-queries" placeholder="Systemadministrator&#10;IT-Infrastruktur" style="width:100%;margin:7px 0 14px"></textarea><label style="display:flex;align-items:center;gap:9px;margin:0 0 18px"><input id="source-enabled" type="checkbox" checked style="min-width:auto"> Quelle aktiv</label><div class="actions"><button type="button" class="btn" id="source-delete" style="display:none">Löschen</button><button type="submit" class="btn primary">Quelle speichern</button></div></form></div></div>
<script>
const $=id=>document.getElementById(id);let selected=null,jobs=[];const names={neu:"Neu",gemerkt:"Gemerkt",beworben:"Beworben",absage:"Absage",verworfen:"Verworfen"};
const safe=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const date=s=>s?new Date(s).toLocaleDateString("de-DE"):"–";
async function api(path,options={}){const r=await fetch(path,{headers:{"Content-Type":"application/json"},...options});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail||r.statusText);return r.json()}
function render(){const q=$("search").value.trim().toLowerCase(),st=$("status").value,min=Number($("minimum").value||0);const shown=jobs.filter(j=>(!st||j.status===st)&&(!min||(j.score??0)>=min)&&(!q||[j.title,j.company,j.location].some(v=>(v||"").toLowerCase().includes(q))));$("result-count").textContent=shown.length+" Treffer";$("jobs").innerHTML=shown.length?shown.map(j=>'<article class="job" data-id="'+safe(j.id)+'"><div><h4>'+safe(j.title)+'</h4><div class="company">'+safe(j.company||"Unternehmen unbekannt")+'</div><div class="meta"><span>⌖ '+safe(j.location||"Ort offen")+'</span><span>'+safe(names[j.status]||j.status)+'</span><span>Zuletzt gesehen: '+date(j.last_seen_at)+'</span></div></div><div class="score">'+(j.score??"–")+'<small style="display:block;font-size:9px;font-weight:500">MATCH</small></div></article>').join(""):'<div class="empty">Keine passenden Stellen gefunden.</div>';document.querySelectorAll(".job").forEach(el=>el.addEventListener("click",()=>openJob(el.dataset.id)))}
let sourceItems=[],editingSource=null;async function loadSources(){try{const data=await api("api/sources");sourceItems=data.items;$("sources").innerHTML=sourceItems.length?sourceItems.map(s=>'<div class="status-row" style="align-items:center;gap:8px"><span><b style="color:var(--text)">'+safe(s.name)+'</b><small style="display:block;color:var(--muted)">'+safe(({web:"Web",api:"API",email:"E-Mail",manual:"Manuell"})[s.source_type]||s.source_type)+' · '+(s.enabled?"Aktiv":"Pausiert")+'</small></span><button class="btn" data-source="'+safe(s.id)+'" style="padding:5px 8px">Bearbeiten</button></div>').join(""):'<div class="muted">Noch keine Quellen angelegt.</div>';document.querySelectorAll("[data-source]").forEach(b=>b.onclick=()=>editSource(b.dataset.source))}catch(e){$("sources").textContent="Quellen konnten nicht geladen werden: "+e.message}}function editSource(id){editingSource=sourceItems.find(s=>s.id===id)||null;$("source-heading").textContent=editingSource?"Quelle bearbeiten":"Quelle hinzufügen";$("source-id").value=editingSource?.id||"";$("source-id").disabled=!!editingSource;$("source-name").value=editingSource?.name||"";$("source-type").value=editingSource?.source_type||"web";$("source-url").value=editingSource?.base_url||"";$("source-queries").value=(editingSource?.queries||[]).join("\n");$("source-enabled").checked=editingSource?.enabled??true;$("source-delete").style.display=editingSource?"inline-block":"none";$("source-detail").classList.add("open")}async function saveSource(e){e.preventDefault();const id=$("source-id").value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g,"-");if(!id){alert("Bitte eine gültige ID eingeben.");return}const payload={name:$("source-name").value.trim(),source_type:$("source-type").value,base_url:$("source-url").value.trim()||null,enabled:$("source-enabled").checked,queries:$("source-queries").value.split("\n").map(x=>x.trim()).filter(Boolean),config:{}};try{await api("api/sources/"+encodeURIComponent(id),{method:"PUT",body:JSON.stringify(payload)});$("source-detail").classList.remove("open");await loadSources()}catch(e){alert("Quelle konnte nicht gespeichert werden: "+e.message)}}async function deleteSource(){if(!editingSource||!confirm("Quelle \""+editingSource.name+"\" wirklich löschen?"))return;try{await api("api/sources/"+encodeURIComponent(editingSource.id),{method:"DELETE"});$("source-detail").classList.remove("open");await loadSources()}catch(e){alert("Löschen fehlgeschlagen: "+e.message)}}$("add-source").onclick=()=>editSource(null);$("source-close").onclick=()=>$("source-detail").classList.remove("open");$("source-form").onsubmit=saveSource;$("source-delete").onclick=deleteSource;\nasync function refresh(){try{const pair=await Promise.all([api("api/overview"),api("api/jobs?limit=200")]);const o=pair[0];jobs=pair[1].items;$("total").textContent=o.jobs_total;$("new").textContent=o.jobs_by_status.neu||0;$("saved").textContent=o.jobs_by_status.gemerkt||0;$("average").textContent=o.average_score==null?"–":o.average_score;$("status-list").innerHTML=Object.entries(names).map(([k,v])=>'<div class="status-row"><span>'+v+'</span><b>'+(o.jobs_by_status[k]||0)+'</b></div>').join("");$("last-run").innerHTML=o.latest_run?'<strong>'+safe(o.latest_run.status)+'</strong><br>'+date(o.latest_run.started_at)+'<br>'+o.latest_run.jobs_found+' Anzeigen gefunden · '+o.latest_run.jobs_new+' neu':"Noch keine Suchläufe erfasst.";$("updated").textContent="Aktualisiert: "+new Date().toLocaleTimeString("de-DE",{hour:"2-digit",minute:"2-digit"});render()}catch(e){$("jobs").innerHTML='<div class="empty">Daten konnten nicht geladen werden: '+safe(e.message)+'</div>';$("updated").textContent="Verbindung fehlgeschlagen"}}
async function openJob(id){try{selected=await api("api/jobs/"+encodeURIComponent(id));$("detail-title").textContent=selected.title;$("detail-company").textContent=selected.company||"Unternehmen unbekannt";$("detail-meta").textContent=[selected.location,selected.source,selected.score!=null?selected.score+" Match-Punkte":null].filter(Boolean).join(" · ");$("detail-status").value=selected.status;$("detail-notes").value=selected.notes||"";$("source-link").href=selected.url||"#";$("source-link").style.visibility=selected.url?"visible":"hidden";$("detail").classList.add("open")}catch(e){alert(e.message)}}
$("close").onclick=()=>$("detail").classList.remove("open");$("detail").addEventListener("click",e=>{if(e.target===$("detail"))$("detail").classList.remove("open")});$("save").onclick=async()=>{if(!selected)return;try{await api("api/jobs/"+encodeURIComponent(selected.id),{method:"PATCH",body:JSON.stringify({status:$("detail-status").value,notes:$("detail-notes").value})});$("detail").classList.remove("open");await refresh()}catch(e){alert("Speichern fehlgeschlagen: "+e.message)}};["search","status","minimum"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",render));refresh();loadSources();
</script></body></html>"""


@app.get("/api/health")
def health() -> dict[str, str]:
    ready = database_is_ready()
    return {"status": "ok" if ready else "degraded", "service": "jobradar", "database": "ready" if ready else "not_ready"}


@app.get("/api/meta")
def metadata() -> dict[str, str]:
    return {"name": "Jobradar", "version": app.version, "mode": "standalone"}


@app.get("/api/jobs")
def list_jobs(
    status: JobStatus | None = None,
    q: str | None = Query(default=None, max_length=200),
    min_score: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])
    if min_score is not None:
        clauses.append("COALESCE(score, 0) >= ?")
        params.append(min_score)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM jobs {where} ORDER BY COALESCE(score, 0) DESC, first_seen_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreate) -> dict[str, Any]:
    now = now_iso()
    job_id = str(uuid4())
    data = payload.model_dump()
    with connect() as db:
        db.execute(
            """INSERT INTO jobs
            (id,title,company,location,url,source,description,salary_min,salary_max,remote_type,score,
             status,notes,published_at,first_seen_at,last_seen_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'neu','',?,?,?,?,?)""",
            (job_id, data["title"], data["company"], data["location"], data["url"], data["source"],
             data["description"], data["salary_min"], data["salary_max"], data["remote_type"],
             data["score"], data["published_at"], now, now, now, now),
        )
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Stelle nicht gefunden")
    return dict(row)


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: str, payload: JobPatch) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Keine Änderungen übergeben")
    if all(value is None for value in changes.values()):
        raise HTTPException(status_code=400, detail="Änderungswerte dürfen nicht null sein")
    changes["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in changes)
    with connect() as db:
        cursor = db.execute(
            f"UPDATE jobs SET {assignments} WHERE id = ?",
            [*changes.values(), job_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Stelle nicht gefunden")
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@app.get("/api/profile")
def get_profile() -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT data_json, updated_at FROM profile WHERE id = 1").fetchone()
    if row is None:
        return {"data": {}, "updated_at": None}
    return {"data": json.loads(row["data_json"]), "updated_at": row["updated_at"]}


@app.put("/api/profile")
def save_profile(payload: ProfileUpdate) -> dict[str, Any]:
    updated = now_iso()
    with connect() as db:
        db.execute(
            """INSERT INTO profile (id, data_json, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at""",
            (json.dumps(payload.data, ensure_ascii=False), updated),
        )
    return {"data": payload.data, "updated_at": updated}


@app.get("/api/rules")
def list_rules() -> dict[str, list[dict[str, Any]]]:
    with connect() as db:
        rows = db.execute("SELECT id, data_json, updated_at FROM search_rules ORDER BY id").fetchall()
    return {"items": [{"id": row["id"], "data": json.loads(row["data_json"]), "updated_at": row["updated_at"]} for row in rows]}


@app.put("/api/rules/{rule_id}")
def save_rule(rule_id: str, payload: RuleUpdate) -> dict[str, Any]:
    if not rule_id.strip() or len(rule_id) > 100:
        raise HTTPException(status_code=400, detail="Ungültige Regel-ID")
    updated = now_iso()
    with connect() as db:
        db.execute(
            """INSERT INTO search_rules (id, data_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at""",
            (rule_id, json.dumps(payload.data, ensure_ascii=False), updated),
        )
    return {"id": rule_id, "data": payload.data, "updated_at": updated}


class RunCreate(BaseModel):
    started_at: str | None = None


class RunFinish(BaseModel):
    status: Literal["success", "partial", "failed"]
    jobs_found: int = Field(default=0, ge=0)
    jobs_new: int = Field(default=0, ge=0)
    error_summary: str | None = Field(default=None, max_length=2000)


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    with connect() as db:
        counts = {
            row["status"]: row["count"]
            for row in db.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status")
        }
        total = sum(counts.values())
        average = db.execute("SELECT AVG(score) FROM jobs WHERE score IS NOT NULL").fetchone()[0]
        latest_run = db.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        recent_jobs = db.execute(
            "SELECT id, title, company, location, score, status, first_seen_at FROM jobs ORDER BY first_seen_at DESC LIMIT 5"
        ).fetchall()
    return {
        "jobs_total": total,
        "jobs_by_status": counts,
        "average_score": round(average, 1) if average is not None else None,
        "latest_run": dict(latest_run) if latest_run else None,
        "recent_jobs": [dict(row) for row in recent_jobs],
    }


@app.get("/api/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.post("/api/runs", status_code=201)
def create_run(payload: RunCreate) -> dict[str, Any]:
    started = payload.started_at or now_iso()
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (started,),
        )
        row = db.execute("SELECT * FROM runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.post("/api/runs/{run_id}/finish")
def finish_run(run_id: int, payload: RunFinish) -> dict[str, Any]:
    finished = now_iso()
    with connect() as db:
        cursor = db.execute(
            """UPDATE runs SET finished_at = ?, status = ?, jobs_found = ?,
            jobs_new = ?, error_summary = ? WHERE id = ? AND status = 'running'""",
            (finished, payload.status, payload.jobs_found, payload.jobs_new,
             payload.error_summary, run_id),
        )
        if cursor.rowcount == 0:
            exists = db.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="Suchlauf nicht gefunden")
            raise HTTPException(status_code=409, detail="Suchlauf wurde bereits abgeschlossen")
        row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row)


class SourceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["web", "api", "email", "manual"] = "web"
    base_url: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    queries: list[str] = Field(default_factory=list, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/sources")
def list_sources() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM job_sources ORDER BY enabled DESC, name COLLATE NOCASE"
        ).fetchall()
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "source_type": row["source_type"],
                "base_url": row["base_url"],
                "enabled": bool(row["enabled"]),
                "queries": json.loads(row["query_json"]),
                "config": json.loads(row["config_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    }


@app.put("/api/sources/{source_id}")
def save_source(source_id: str, payload: SourceUpdate) -> dict[str, Any]:
    if not source_id.strip() or len(source_id) > 100:
        raise HTTPException(status_code=400, detail="Ungültige Quellen-ID")
    updated = now_iso()
    with connect() as db:
        db.execute(
            """INSERT INTO job_sources
            (id, name, source_type, base_url, enabled, query_json, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, source_type=excluded.source_type, base_url=excluded.base_url,
            enabled=excluded.enabled, query_json=excluded.query_json,
            config_json=excluded.config_json, updated_at=excluded.updated_at""",
            (
                source_id, payload.name, payload.source_type, payload.base_url,
                int(payload.enabled), json.dumps(payload.queries, ensure_ascii=False),
                json.dumps(payload.config, ensure_ascii=False), updated, updated,
            ),
        )
    return {
        "id": source_id,
        **payload.model_dump(),
        "updated_at": updated,
    }


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(source_id: str) -> None:
    with connect() as db:
        cursor = db.execute("DELETE FROM job_sources WHERE id = ?", (source_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Quelle nicht gefunden")
