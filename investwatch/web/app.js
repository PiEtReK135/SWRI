const byId = id => document.getElementById(id);
function node(tag, label, parent) {
  const element = document.createElement(tag);
  element.textContent = label ?? "";
  if (parent) parent.append(element);
  return element;
}
async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : response.statusText);
  }
  return response.json();
}
function time(ms) {
  if (ms == null) return "—";
  return new Date(ms).toISOString().slice(14, 19);
}
function link(parent, title, url) {
  const a = node("a", title, parent);
  a.href = url;
  return a;
}
async function openItem(id) {
  const item = await api("/content/" + id);
  const root = byId("review");
  root.replaceChildren();
  node("h2", item.metadata.title || item.metadata.url || "Materiał", root);
  node("p", [item.metadata.is_demo ? "DEMO" : "", item.metadata.creator, item.status, item.reason]
    .filter(Boolean).join(" · "), root);
  if (/^https?:\/\//i.test(item.metadata.url)) link(root, "Źródło", item.metadata.url).rel = "noreferrer";
  const video = item.metadata.media ? node("video", "", root) : null;
  if (video) {
    video.controls = true;
    video.preload = "metadata";
    video.src = "/artifacts/" + id + "/" + item.metadata.media;
  }
  const report = item.report;
  if (!report) return;
  node("h3", "Dowody", root);
  const list = node("ul", "", root);
  for (const evidence of report.evidence) {
    const line = node("li", evidence.kind + " · " + evidence.quote, list);
    if (evidence.start_ms != null) {
      const button = node("button", time(evidence.start_ms), line);
      button.disabled = !video;
      button.onclick = () => { video.currentTime = evidence.start_ms / 1000; };
    }
    if (evidence.artifact) link(line, " Klatka", "/artifacts/" + id + "/" + evidence.artifact);
  }
  if (!report.evidence.length) node("li", "Brak sygnałów w dostępnych danych", list);
  for (const gap of report.limitations) node("p", gap, root);
  const rules = node("details", "", root);
  node("summary", "Reguły i przesłanki", rules);
  for (const rule of report.rule_evaluations) node("p", rule.rule_id + " · " + rule.status + " · " + rule.why, rules);
  const timeline = node("details", "", root);
  node("summary", "Oś czasu", timeline);
  for (const row of report.timeline) node("p", time(row.start_ms) + " · " + row.kind + " · " + row.quote, timeline);
  link(root, "Raport JSON", "/reports/" + id);
  node("span", " · ", root);
  link(root, "Raport HTML", "/reports/" + id + "?format=html");
  window.reviewTools?.(item, root);
}
async function refresh() {
  const items = await api("/content");
  const target = byId("items");
  target.replaceChildren();
  for (const item of items.filter(item => !window.itemFilter || window.itemFilter(item))) {
    const row = node("tr", "", target);
    const button = node("button", item.metadata.title || item.metadata.url || item.id.slice(0, 8),
      node("td", item.metadata.is_demo ? "DEMO " : "", row));
    button.onclick = () => openItem(item.id).catch(showError);
    node("td", item.status, row);
    node("td", item.report?.modules.join(", "), row);
    node("td", item.report?.coverage.join(", "), row);
    node("td", item.report?.priority_score, row);
  }
}
function showError(error) { byId("status").textContent = error.message; }
byId("upload").onsubmit = async event => {
  event.preventDefault();
  const body = new FormData(event.target);
  for (const key of ["video", "subtitle"]) if (!body.get(key).name) body.delete(key);
  try {
    const result = await api("/import/video", {method: "POST", body});
    byId("status").textContent = result.duplicate ? "Materiał już znajduje się w kolejce." : "Dodano materiał.";
    await refresh();
  } catch (error) { showError(error); }
};
refresh().catch(showError);
setInterval(() => refresh().catch(showError), 4000);

function jsonOptions(method, data) {
  return {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)};
}
const tools = byId("tools");
const discovery = node("section", "", tools);
node("h2", "Discovery", discovery);
node("p", "Import lokalny i metadane. Dostęp platformowy wymaga autoryzacji.", discovery);
const plans = node("ul", "", discovery);
function showPlans(queries) {
  plans.replaceChildren();
  for (const query of queries.slice(0, 12)) node("li", query.query + " · " + query.sampling_stratum, plans);
}
node("button", "Zaplanuj wyszukiwanie", discovery).onclick = async () => {
  try { showPlans(await api("/discovery/run", {method: "POST"})); }
  catch (error) { showError(error); }
};
node("button", "Wczytaj filmy demo", discovery).onclick = async event => {
  const button = event.target;
  button.disabled = true;
  try {
    await api("/demo/run", {method: "POST"});
    await refresh();
  } catch (error) { showError(error); }
  finally { button.disabled = false; }
};
const seedForm = node("form", "", discovery);
const seedFile = node("input", "", seedForm);
Object.assign(seedFile, {name: "file", type: "file", accept: ".csv,.json", required: true});
const rights = node("label", "", seedForm);
const seedRights = node("input", "", rights);
Object.assign(seedRights, {name: "rights_confirmed", type: "checkbox", value: "true", required: true});
rights.append(" Mam prawo do importu metadanych");
node("button", "Importuj listę URL", seedForm);
seedForm.onsubmit = async event => {
  event.preventDefault();
  try { await api("/import/urls", {method: "POST", body: new FormData(seedForm)}); await refresh(); }
  catch (error) { showError(error); }
};
const watchForm = node("form", "", discovery);
const watchKind = node("select", "", watchForm);
node("option", "CREATORS", watchKind);
node("option", "ENTITIES", watchKind);
const watchName = node("input", "", watchForm);
const watchReason = node("input", "", watchForm);
Object.assign(watchName, {placeholder: "Twórca lub firma", required: true});
Object.assign(watchReason, {placeholder: "Uzasadnienie obserwacji", required: true});
node("button", "Obserwuj", watchForm);
watchForm.onsubmit = async event => {
  event.preventDefault();
  try {
    await api("/watchlist", jsonOptions("POST", {kind: watchKind.value, name: watchName.value,
      reason: watchReason.value}));
    watchForm.reset();
  } catch (error) { showError(error); }
};
api("/discovery/queries").then(showPlans).catch(showError);

const calibrate = node("section", "", tools);
node("h2", "Alerty", calibrate);
const filter = node("select", "", byId("filters"));
for (const value of ["Wszystkie", "M1", "M2", "M3", "ACTION_REQUIRED"]) node("option", value, filter);
window.itemFilter = item => filter.value === "Wszystkie" || item.status === filter.value ||
  item.report?.modules.includes(filter.value);
filter.onchange = () => refresh().catch(showError);
const summary = node("p", "", calibrate);
const thresholdLabel = node("label", "Próg priorytetu ", calibrate);
const slider = node("input", "", thresholdLabel);
Object.assign(slider, {type: "range", min: 0, max: 100, value: 55});
const targetAlerts = node("ul", "", calibrate);
const trend = node("div", "", calibrate);
async function metrics() {
  const [counts, alerts] = await Promise.all([api("/metrics"), api("/alerts")]);
  slider.value = counts.threshold;
  summary.textContent = "Próg " + counts.threshold + " · " + counts.alerts + " materiałów powyżej progu";
  trend.replaceChildren();
  for (const point of counts.trend || []) {
    const label = node("label", point.day + " · " + point.alerts, trend);
    const bar = node("meter", "", label);
    bar.max = Math.max(1, ...counts.trend.map(day => day.alerts));
    bar.value = point.alerts;
  }
  targetAlerts.replaceChildren();
  for (const alert of alerts.slice(0, 8)) {
    const item = node("li", "", targetAlerts);
    node("button", alert.status, item).onclick = () => openItem(alert.job).catch(showError);
    item.append(" " + (alert.reason || ""));
  }
}
slider.onchange = async () => {
  try {
    await api("/settings/threshold", jsonOptions("PATCH", {threshold: Number(slider.value)}));
    await metrics();
  } catch (error) { showError(error); }
};
link(calibrate, "Eksport CSV", "/reports.csv");

window.reviewTools = (item, root) => {
  const form = node("form", "", root);
  node("h3", "Ocena operatora", form);
  const state = node("select", "", form);
  for (const value of ["NEW", "IN_REVIEW", "CONFIRMED_EVIDENCE", "DISMISSED"]) node("option", value, state);
  state.value = item.review;
  const operator = node("input", "", form);
  Object.assign(operator, {placeholder: "Operator", value: item.operator || "", required: true});
  const note = node("textarea", "", form);
  Object.assign(note, {placeholder: "Uzasadnienie", value: item.note || ""});
  node("button", "Zapisz ocenę", form);
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      await api("/cases/" + item.id, jsonOptions("PATCH", {review: state.value,
        operator: operator.value, note: note.value}));
      await openItem(item.id);
    } catch (error) { showError(error); }
  };
  if (/^https?:\/\//i.test(item.metadata.url)) {
    const observation = node("form", "", root);
    node("h3", "Stan źródła", observation);
    const state = node("select", "", observation);
    for (const option of ["AVAILABLE", "CHANGED", "UNAVAILABLE", "CAPTCHA", "LOGIN", "403", "429"]) {
      node("option", option, state);
    }
    const note = node("input", "", observation);
    note.placeholder = "Uwagi po sprawdzeniu źródła";
    node("button", "Zapisz stan źródła", observation);
    observation.onsubmit = async event => {
      event.preventDefault();
      try {
        await api("/content/" + item.id + "/source-observation",
          jsonOptions("POST", {status: state.value, note: note.value}));
        await metrics();
      } catch (error) { showError(error); }
    };
  }
  node("button", "Ponów analizę lokalną", root).onclick = async () => {
    try { await api("/jobs/" + item.id + "/retry", {method: "POST"}); await refresh(); }
    catch (error) { showError(error); }
  };
};
metrics().catch(showError);
const events = new EventSource("/events/stream");
events.onmessage = event => {
  const change = JSON.parse(event.data);
  if (["COMPLETED", "ACTION_REQUIRED", "FAILED", "SOURCE_BLOCKED", "RECHECK_REQUIRED"].includes(change.status)) {
    refresh().catch(showError);
    metrics().catch(showError);
  }
};

const health = node("section", "", tools);
node("h2", "Narzędzia lokalne", health);
api("/health").then(state => node("p", "FFmpeg: " + (state.ffmpeg ? "dostępny" : "brak") +
  " · OCR: " + (state.tesseract ? "dostępny" : "brak"), health)).catch(showError);

const directories = node("details", "", tools);
node("summary", "Twórcy i firmy", directories);
directories.addEventListener("toggle", async () => {
  if (!directories.open) return;
  try {
    const [creators, entities] = await Promise.all([api("/creators"), api("/entities")]);
    directories.querySelector("ul")?.remove();
    const list = node("ul", "", directories);
    for (const creator of creators) node("li", creator, list);
    for (const entity of entities) node("li", entity.name + " · " + entity.registry_status, list);
  } catch (error) { showError(error); }
});
