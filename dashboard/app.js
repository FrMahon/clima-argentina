/* Clima de Argentina — página de datos sobre data.json (generado por `clima export`). */
/* global Plot, d3 */

const state = {
  data: null,
  geo: null,
  metric: "temperatura",
  view: "puntos", // "puntos" | "calor"
  selected: null, // ciudad con la ficha abierta
  hovered: null,  // ciudad bajo el cursor (mapa o lista)
  year: null,     // año elegido en la línea de tiempo
  preview: null,  // año bajo el cursor en las franjas (vista previa, no cambia `year`)
  timer: null,
  stripesIntro: false, // animación de entrada de las franjas (solo el primer dibujo)
  mapIntro: false,     // animación de entrada del mapa (solo cuando aparece por primera vez)
};

// --- Animaciones de entrada ----------------------------------------------------------------
// El script del <head> pone `js-anim` solo si el sistema no pide reducir movimiento.

const animating = () => document.documentElement.classList.contains("js-anim");

// Numera los hijos de una lista para que entren uno después del otro (ver `.stagger` en el CSS).
function indexChildren(parent) {
  [...parent.children].forEach((child, i) => child.style.setProperty("--i", i));
}

function setupReveals() {
  window.__revealReady = true;
  if (!animating()) return;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const target = entry.target;
        target.classList.add("is-in");
        observer.unobserve(target);
        if (target.classList.contains("map-col")) {
          state.mapIntro = true;
          renderMap(tokens()); // se redibuja con la animación de norte a sur
          state.mapIntro = false;
        }
      }
    },
    { threshold: 0.15, rootMargin: "0px 0px -6% 0px" },
  );
  document.querySelectorAll(".reveal, .stagger").forEach((el) => observer.observe(el));
}

// --- Formato (es-AR) -----------------------------------------------------------------

const nf = (d) => new Intl.NumberFormat("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt = (v, d = 1) => (v == null ? "—" : nf(d).format(v));
const signed = (v, d = 1) => {
  if (v == null) return "—";
  const r = Number(v.toFixed(d));
  return (r > 0 ? "+" : r < 0 ? "−" : "") + nf(d).format(Math.abs(r));
};
// Espacio que no se corta: "0,1 °C" nunca queda partido en dos renglones.
const degC = (v, d = 1) => `${signed(v, d)} °C`;
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

const isNarrow = () => window.matchMedia("(max-width: 520px)").matches;
const NAMES = { tucuman: "Tucumán", bariloche: "Bariloche" };
const NARROW_NAMES = { comodoro_rivadavia: "C. Rivadavia" };
const shortName = (id, full) => (isNarrow() && NARROW_NAMES[id]) || NAMES[id] || full;

// --- Indicadores -------------------------------------------------------------------------
// warm: +1 si "más" es más cálido (temperatura, días de calor); −1 si "más" es más frío (heladas).
// El color siempre significa lo mismo: rojo = cambio hacia más calor.

const METRICS = {
  temperatura: { label: "Temperatura", kind: "temp", warm: 1, what: "la temperatura media del año", ends: ["Más frío", "Más cálido"] },
  verano: { label: "Verano", kind: "temp", warm: 1, what: "la temperatura media del verano (diciembre a febrero)", ends: ["Más frío", "Más cálido"] },
  invierno: { label: "Invierno", kind: "temp", warm: 1, what: "la temperatura media del invierno (junio a agosto)", ends: ["Más frío", "Más cálido"] },
  dias_calor: { label: "Días de calor", kind: "days", warm: 1, what: "los días por año con máxima de 30 °C o más", ends: ["Menos días de calor", "Más días de calor"] },
  heladas: { label: "Heladas", kind: "days", warm: -1, what: "los días por año con mínima bajo cero", ends: ["Más heladas", "Menos heladas"] },
  noches_tropicales: { label: "Noches cálidas", kind: "days", warm: 1, what: "las noches por año con mínima de 20 °C o más", ends: ["Menos noches cálidas", "Más noches cálidas"] },
};

const metric = () => METRICS[state.metric];
const fmtChange = (m, v) => (m.kind === "temp" ? degC(v) : `${signed(v, 0)} días`);
const fmtLevel = (m, v) => (m.kind === "temp" ? `${fmt(v)} °C` : fmt(v, 0));

// Media de 10 años de la diferencia con 1961–1990, para una ciudad y un año.
function changeAt(cityId, year, key = state.metric) {
  const s = state.data.indicators[key]?.[cityId];
  if (!s) return null;
  const i = s.year.indexOf(year);
  return i >= 0 ? s.rolling[i] : null;
}

// Amplitud de la escala de color: fija en ±2 °C para temperaturas (igual que las franjas del país);
// para días, se ajusta a los datos de ese indicador y se redondea a múltiplos de 5.
const domainCache = {};
function domainFor(key) {
  if (domainCache[key]) return domainCache[key];
  const m = METRICS[key];
  if (m.kind === "temp") return (domainCache[key] = 2);
  const values = Object.values(state.data.indicators[key] ?? {}).flatMap((s) => s.rolling.filter((v) => v != null).map(Math.abs));
  const q = d3.quantile(values.sort(d3.ascending), 0.98) ?? 5;
  return (domainCache[key] = Math.max(5, Math.ceil(q / 5) * 5));
}

// --- Color -----------------------------------------------------------------------------

function tokens() {
  const s = getComputedStyle(document.documentElement);
  const v = (n) => s.getPropertyValue(n).trim();
  const dark = s.colorScheme === "dark";
  return {
    paper: v("--paper"),
    ink: v("--ink"),
    ink2: v("--ink-2"),
    rule: v("--rule"),
    land: v("--land"),
    ramp: dark
      ? ["#86b6ef", "#2a78d6", v("--mid"), "#e34948", "#f1a3a2"]
      : ["#104281", "#6da7ec", v("--mid"), "#ee8f8c", "#8f1d22"],
  };
}

const stops = (D) => [-D, -D / 2, 0, D / 2, D];
const plotColor = (T, D = 2) => ({ type: "linear", domain: stops(D), range: T.ramp, interpolate: "lab", clamp: true });
const colorFn = (T, D = 2) => d3.scaleLinear().domain(stops(D)).range(T.ramp).interpolate(d3.interpolateLab).clamp(true);

const plotStyle = (T) => ({ fontSize: "13px", fontFamily: "inherit", color: T.ink2, background: "transparent", overflow: "visible" });
const tip = (T) => ({ fill: T.paper, stroke: T.rule, textPadding: 8, lineHeight: 1.35, fontSize: 13 });

// --- Datos -------------------------------------------------------------------------------

function nationalSeries() {
  const src = state.data.regions.Argentina;
  return src ? src.year.map((year, i) => ({ year, anomaly: src.anomaly[i] })) : [];
}

function citySeries(cityId, key = state.metric) {
  const s = state.data.indicators[key]?.[cityId];
  return s ? s.year.map((year, i) => ({ year, change: s.change[i] })) : [];
}

const warmingOf = (id) => state.data.warming.find((w) => w.city_id === id);
const hasData = (id) => Boolean(warmingOf(id));
const shownYear = () => state.preview ?? state.year;

// --- DOM ---------------------------------------------------------------------------------

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") Object.assign(node.style, v);
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const $ = (id) => document.getElementById(id);
const widthOf = (id) => Math.max(260, $(id).clientWidth);

// --- Apertura ----------------------------------------------------------------------------

function renderOpening() {
  const { warming, meta } = state.data;
  const avg = mean(warming.map((w) => w.warming_c));
  const [r0, r1] = meta.recent;

  $("headline").textContent =
    Math.abs(avg) < 0.05
      ? "En la última década, Argentina tuvo casi la misma temperatura que entre 1961 y 1990."
      : `En la última década, Argentina estuvo ${fmt(Math.abs(avg))} °C más ${avg > 0 ? "cálida" : "fría"} que entre 1961 y 1990.`;
  $("dek").textContent =
    `Promedio de ${warming.length} ciudades, de Salta a Ushuaia, entre ${r0} y ${r1}. ` +
    `Abajo, la temperatura de cada año desde ${meta.first_year}.`;
  $("first-year").textContent = meta.first_year;
  $("last-year").textContent = meta.last_year;
}

// Al pasar el cursor por unas franjas, el mapa y la lista muestran ese año (vista previa).
function linkToPreview(plot) {
  const firstRolling = state.data.meta.first_year + 9;
  plot.addEventListener("input", () => {
    const year = plot.value?.year ?? null;
    const next = year != null && year >= firstRolling ? year : null;
    if (next === state.preview) return;
    state.preview = next;
    const T = tokens();
    renderMap(T);
    renderList(T);
    renderYearLabel();
  });
}

function renderNationalStripes(T) {
  const series = nationalSeries();
  const plot = Plot.plot({
    width: widthOf("national-stripes"),
    height: isNarrow() ? 110 : 180,
    margin: 0,
    x: { axis: null },
    y: { axis: null },
    color: plotColor(T),
    style: plotStyle(T),
    marks: [
      Plot.rectX(series, { x1: "year", x2: (d) => d.year + 1, y1: 0, y2: 1, fill: "anomaly" }),
      Plot.ruleX(series, Plot.pointerX({ x: (d) => d.year + 0.5, y1: 0, y2: 1, stroke: T.ink, strokeWidth: 1.5 })),
      Plot.tip(
        series,
        Plot.pointerX({ x: (d) => d.year + 0.5, y: 0.5, title: (d) => `${d.year}\n${degC(d.anomaly)} respecto de 1961–1990`, ...tip(T) }),
      ),
    ],
  });
  linkToPreview(plot);
  if (state.stripesIntro) {
    // Cada franja entra 14 ms después de la anterior: el país se "pinta" de 1940 a hoy.
    plot.classList.add("stripes-intro");
    plot.querySelectorAll('g[aria-label="rect"] rect').forEach((r, i) => r.style.setProperty("--d", `${450 + i * 14}ms`));
    state.stripesIntro = false;
  }
  $("national-stripes").replaceChildren(plot);
}

// --- Selector "qué ver" --------------------------------------------------------------------

function renderPicker() {
  $("metric-picker").replaceChildren(
    ...Object.entries(METRICS).map(([key, m]) =>
      el("button", { type: "button", role: "radio", "aria-checked": String(key === state.metric), onclick: () => setMetric(key) }, m.label),
    ),
  );
  indexChildren($("metric-picker"));
}

function setMetric(key) {
  if (!METRICS[key] || key === state.metric) return;
  state.metric = key;
  writeHash();
  renderPicker();
  const T = tokens();
  renderMap(T);
  renderList(T);
  renderDetail(T);
}

// --- Mapa de calor: grilla + interpolación ---------------------------------------------------
// Grilla de celdas de 0,5° sobre el país. El valor de cada celda se estima con IDW (distancia
// inversa al cuadrado) a partir de las ciudades: es una estimación visual, no una medición.

const CELL = 0.5;
let heatGrid = null;

function buildHeatGrid() {
  const country = state.geo.features.find((f) => f.properties.kind === "country");
  const cities = state.data.cities;
  const cells = [];
  for (let lon = -74; lon < -53; lon += CELL) {
    for (let lat = -56; lat < -21; lat += CELL) {
      const corners = [[lon, lat], [lon + CELL, lat], [lon + CELL, lat + CELL], [lon, lat + CELL], [lon + CELL / 2, lat + CELL / 2]];
      if (!corners.some((p) => d3.geoContains(country, p))) continue;
      const center = [lon + CELL / 2, lat + CELL / 2];
      // Pesos fijos por ciudad (1/d²): se calculan una vez y se reusan en cada año e indicador.
      const weights = cities.map((c) => {
        const d = d3.geoDistance(center, [c.longitude, c.latitude]);
        return 1 / Math.max(d * d, 1e-8);
      });
      cells.push({
        type: "Feature",
        // Sentido horario: d3-geo interpreta el anillo antihorario como "todo el globo menos la celda".
        geometry: { type: "Polygon", coordinates: [[[lon, lat], [lon, lat + CELL], [lon + CELL, lat + CELL], [lon + CELL, lat], [lon, lat]]] },
        weights,
      });
    }
  }
  return cells;
}

function heatCells(values) {
  heatGrid ??= buildHeatGrid();
  return heatGrid.map((cell) => {
    let num = 0;
    let den = 0;
    values.forEach((v, i) => {
      if (v == null) return;
      num += cell.weights[i] * v;
      den += cell.weights[i];
    });
    return { ...cell, warmth: den ? num / den : null };
  });
}

function setupViewToggle() {
  const buttons = document.querySelectorAll("#view-toggle button");
  const sync = () => buttons.forEach((b) => b.setAttribute("aria-checked", String(b.dataset.view === state.view)));
  buttons.forEach((b) =>
    b.addEventListener("click", () => {
      state.view = b.dataset.view;
      sync();
      writeHash();
      renderMap(tokens());
    }),
  );
  sync();
}

// --- Mapa --------------------------------------------------------------------------------

// Dónde va el nombre de cada ciudad (por defecto a la derecha), para que no se pisen ni se salgan.
const LABEL_SIDE = { posadas: "top", corrientes: "left", buenos_aires: "left" };
const OFFSETS = { right: [13, 0, "start"], left: [-13, 0, "end"], top: [0, -16, "middle"] };

function renderMap(T) {
  const m = metric();
  const D = domainFor(state.metric);
  const year = shownYear();
  const provinces = state.geo.features.filter((f) => f.properties.kind === "province");
  const country = state.geo.features.find((f) => f.properties.kind === "country");
  const points = state.data.cities.map((c) => {
    const change = changeAt(c.id, year);
    return {
      id: c.id,
      name: shortName(c.id, c.name),
      full: c.name,
      lon: c.longitude,
      lat: c.latitude,
      change,
      warmth: change == null ? null : change * m.warm, // valor para el color
    };
  });
  const isOn = (d) => d.id === state.selected || d.id === state.hovered;
  const label = (side) =>
    Plot.text(points.filter((d) => (LABEL_SIDE[d.id] ?? "right") === side), {
      x: "lon",
      y: "lat",
      text: "name",
      dx: OFFSETS[side][0],
      dy: OFFSETS[side][1],
      textAnchor: OFFSETS[side][2],
      fill: T.ink,
      stroke: T.land,
      strokeWidth: 4,
      strokeLinejoin: "round",
      fontSize: 13,
    });

  const plot = Plot.plot({
    width: Math.min(440, widthOf("map")),
    projection: { type: "transverse-mercator", rotate: [64, 0], domain: country, inset: 6 },
    r: { type: "identity" },
    color: plotColor(T, D),
    style: plotStyle(T),
    marks: [
      ...(state.view === "calor"
        ? [
            // Capa de calor recortada al contorno del país; el trazo del mismo color tapa las juntas.
            Plot.geo(heatCells(points.map((d) => d.warmth)), {
              fill: "warmth",
              stroke: "warmth",
              strokeWidth: 0.6,
              clip: country,
              className: "heat-layer", // el CSS le aplica un desenfoque suave para disimular la grilla
            }),
            Plot.geo(provinces, { fill: "none", stroke: T.paper, strokeWidth: 0.8, strokeOpacity: 0.75 }),
            Plot.geo(country, { fill: "none", stroke: T.ink2, strokeWidth: 0.8 }),
            // Las ciudades quedan como referencia: puntos neutros, sin repetir el color.
            Plot.dot(points, { x: "lon", y: "lat", r: (d) => (isOn(d) ? 6.5 : 4), fill: (d) => (isOn(d) ? T.ink : T.paper), stroke: T.ink, strokeWidth: 1.5 }),
          ]
        : [
            Plot.geo(country, { fill: T.land }),
            Plot.geo(provinces, { fill: T.land, stroke: T.paper, strokeWidth: 1 }),
            // Aro de contraste: un valor cercano a cero es gris y se perdería sobre la tierra.
            Plot.dot(points, { x: "lon", y: "lat", r: (d) => (isOn(d) ? 12 : 9), fill: (d) => (isOn(d) ? T.ink : T.ink2) }),
            Plot.dot(points, { x: "lon", y: "lat", r: (d) => (isOn(d) ? 10 : 7.5), fill: "warmth", stroke: T.paper, strokeWidth: 1.5 }),
          ]),
      label("right"),
      label("left"),
      label("top"),
      Plot.tip(
        points,
        Plot.pointer({
          x: "lon",
          y: "lat",
          maxRadius: 30,
          title: (d) => `${d.full}\n${d.change == null ? "Sin datos todavía" : `${m.label}: ${fmtChange(m, d.change)}`}`,
          ...tip(T),
        }),
      ),
    ],
  });
  plot.addEventListener("click", () => {
    if (plot.value) select(plot.value.id);
  });
  // Hover en el mapa → resalta la fila de la lista (sin redibujar el mapa, para no perder el puntero).
  plot.addEventListener("input", () => highlightRow(plot.value?.id ?? null));
  $("map").replaceChildren(plot);
  if (state.mapIntro) {
    // Ciudades y nombres aparecen de norte a sur según su altura en el mapa.
    plot.classList.add("map-intro");
    const height = plot.getBoundingClientRect().height || 1;
    const top = plot.getBoundingClientRect().top;
    plot.querySelectorAll("circle, text").forEach((node) => {
      const y = node.getBoundingClientRect().top - top;
      node.style.setProperty("--d", `${300 + (y / height) * 1100}ms`);
    });
  }

  renderScale(T);
  const period = year === state.data.meta.last_year ? "los últimos 10 años" : `los 10 años hasta ${year}`;
  $("map-note").textContent =
    `Color: ${m.what}, promedio de ${period}, comparado con 1961–1990.` +
    (state.view === "calor"
      ? " Entre ciudades, el color es una estimación a partir de las más cercanas, no una medición de cada lugar."
      : "");
}

function renderScale(T) {
  const m = metric();
  const D = domainFor(state.metric);
  const color = colorFn(T, D);
  const gradient = d3.range(0, 1.0001, 0.1).map((t) => color(-D + 2 * D * t)).join(", ");
  // Izquierda = azul (hacia más frío), derecha = rojo (hacia más calor), en todos los indicadores.
  const leftValue = fmtChange(m, -D * m.warm);
  const rightValue = fmtChange(m, D * m.warm);
  $("scale").replaceChildren(
    el("div", { class: "scale-bar", style: { background: `linear-gradient(to right, ${gradient})` } }),
    el("div", { class: "scale-labels" }, [
      el("span", {}, [el("strong", {}, leftValue), ` ${m.ends[0].toLowerCase()}`]),
      el("span", {}, [el("strong", {}, rightValue), ` ${m.ends[1].toLowerCase()}`]),
    ]),
  );
}

// --- Lista de ciudades -----------------------------------------------------------------------

function renderList(T) {
  const m = metric();
  const color = colorFn(T, domainFor(state.metric));
  const last = state.data.meta.last_year;
  const year = shownYear();
  // Orden fijo por el cambio más reciente (no se reordena durante la reproducción).
  // Las ciudades sin datos van siempre al final.
  const score = (id) => {
    const v = changeAt(id, last);
    return v == null ? -Infinity : v * m.warm;
  };
  const order = [...state.data.cities].sort((a, b) => score(b.id) - score(a.id));

  $("city-list").replaceChildren(
    ...order.map((c) => {
      const v = changeAt(c.id, year);
      const available = hasData(c.id);
      return el(
        "li",
        {
          "data-id": c.id,
          class: c.id === state.hovered ? "is-hovered" : "",
          ...(available
            ? {
                onmouseenter: () => setHovered(c.id),
                onmouseleave: () => setHovered(null),
              }
            : {}),
        },
        [
          el(
            "button",
            {
              type: "button",
              "aria-pressed": String(c.id === state.selected),
              ...(available ? { onclick: () => select(c.id), onfocus: () => setHovered(c.id), onblur: () => setHovered(null) } : { disabled: "" }),
            },
            [
              el("span", { class: "swatch", style: { background: v == null ? T.rule : color(v * m.warm) } }),
              el("span", {}, [el("span", { class: "name" }, c.name), el("span", { class: "region" }, c.region)]),
              el("span", { class: "value" }, available && v != null ? fmtChange(m, v) : "sin datos"),
            ],
          ),
        ],
      );
    }),
  );
  indexChildren($("city-list"));
}

function highlightRow(id) {
  state.hovered = id;
  document.querySelectorAll("#city-list li").forEach((li) => li.classList.toggle("is-hovered", li.dataset.id === id));
}

// Hover en la lista → resalta el punto del mapa.
function setHovered(id) {
  if (id === state.hovered) return;
  highlightRow(id);
  renderMap(tokens());
}

// --- Ficha de la ciudad --------------------------------------------------------------------

function renderDetail(T) {
  const box = $("city-detail");
  const w = state.selected && warmingOf(state.selected);
  if (!w) {
    box.replaceChildren();
    return;
  }
  const { meta } = state.data;
  const [r0, r1] = meta.recent;
  const m = metric();
  const D = domainFor(state.metric);

  // Una fila por indicador: valor 1961–1990 → últimos 10 años, y la diferencia.
  const rows = Object.entries(METRICS).map(([key, mm]) => {
    const s = state.data.indicators[key]?.[w.city_id];
    const change = changeAt(w.city_id, meta.last_year, key);
    if (!s || change == null) return null;
    const unit = mm.kind === "temp" ? "" : " días";
    return el("li", {}, [
      el("button", { type: "button", "aria-current": String(key === state.metric), onclick: () => setMetric(key) }, [
        el("span", {}, mm.label),
        el("span", { class: "from-to" }, `${fmtLevel(mm, s.baseline)} → ${fmtLevel(mm, s.baseline + change)}${unit}`),
        el("span", { class: "delta" }, fmtChange(mm, change)),
      ]),
    ]);
  });

  const series = citySeries(w.city_id).map((d) => ({ ...d, warmth: d.change * m.warm }));
  const mini = Plot.plot({
    width: Math.min(760, widthOf("city-detail")),
    height: 56,
    margin: 0,
    x: { axis: null },
    y: { axis: null },
    color: plotColor(T, D),
    style: plotStyle(T),
    marks: [
      Plot.rectX(series, { x1: "year", x2: (d) => d.year + 1, y1: 0, y2: 1, fill: "warmth" }),
      Plot.ruleX(series, Plot.pointerX({ x: (d) => d.year + 0.5, y1: 0, y2: 1, stroke: T.ink, strokeWidth: 1.5 })),
      Plot.tip(
        series,
        Plot.pointerX({ x: (d) => d.year + 0.5, y: 0.5, title: (d) => `${d.year}\n${fmtChange(m, d.change)} respecto de 1961–1990`, ...tip(T) }),
      ),
    ],
  });
  linkToPreview(mini);

  box.replaceChildren(
    el("h3", {}, w.city_name),
    el("p", { class: "where" }, `${w.province}, región ${w.region}. Promedios por año, 1961–1990 → ${r0}–${r1}.`),
    el("ul", { class: "indicators" }, rows),
    el("p", { class: "mini-title" }, `${m.label}, año por año desde ${series[0]?.year ?? meta.first_year}`),
    el("div", { class: "mini", role: "img", "aria-label": `Franjas de ${m.label.toLowerCase()} de ${w.city_name}` }, mini),
    el("div", { class: "mini-ends" }, [el("span", {}, series[0]?.year), el("span", {}, series.at(-1)?.year)]),
  );
}

function select(id) {
  if (!hasData(id)) return;
  state.selected = id;
  writeHash();
  const T = tokens();
  renderMap(T);
  renderList(T);
  renderDetail(T);
}

// --- Línea de tiempo ---------------------------------------------------------------------------

const PLAY = "M4 2.5v11l9-5.5z";
const PAUSE = "M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z";

function renderYearLabel() {
  $("year-out").textContent = shownYear();
}

function setupTimeline() {
  const { meta } = state.data;
  const slider = $("year");
  const first = meta.first_year + 9; // primera media de 10 años completa
  slider.min = first;
  slider.max = meta.last_year;
  slider.value = state.year;
  renderYearLabel();

  const show = (year) => {
    state.year = year;
    state.preview = null;
    slider.value = year;
    renderYearLabel();
    writeHash();
    const T = tokens();
    renderMap(T);
    renderList(T);
  };

  const stop = () => {
    clearInterval(state.timer);
    state.timer = null;
    $("play-icon").setAttribute("d", PLAY);
    $("play").setAttribute("aria-label", "Reproducir la evolución desde 1949");
  };

  $("play").addEventListener("click", () => {
    if (state.timer) return stop();
    if (state.year >= meta.last_year) show(first);
    $("play-icon").setAttribute("d", PAUSE);
    $("play").setAttribute("aria-label", "Pausar");
    state.timer = setInterval(() => (state.year >= meta.last_year ? stop() : show(state.year + 1)), 150);
  });

  slider.addEventListener("input", () => {
    stop();
    show(Number(slider.value));
  });
}

// --- Hallazgos -----------------------------------------------------------------------------------

function renderFindings() {
  const { warming, meta } = state.data;
  const avg = (key) => mean(warming.map((w) => w[key]));
  const avgChange = (key) => {
    const vs = warming.map((w) => changeAt(w.city_id, meta.last_year, key)).filter((v) => v != null);
    return vs.length ? mean(vs) : null;
  };
  const items = [];

  const byRegion = d3.rollups(warming, (ws) => mean(ws.map((w) => w.warming_c)), (w) => w.region).sort((a, b) => b[1] - a[1]);
  if (byRegion.length > 1) {
    const [top, bottom] = [byRegion[0], byRegion.at(-1)];
    items.push([`${top[0]} es la región que más se calentó`, `: ${degC(top[1])}. La que menos, ${bottom[0]}: ${degC(bottom[1])}.`]);
  }

  const summer = avgChange("verano");
  const winter = avgChange("invierno");
  if (summer != null && winter != null) {
    items.push(
      winter > summer
        ? ["El invierno se calentó más que el verano", `: ${degC(winter)} contra ${degC(summer)}, en promedio.`]
        : ["El verano se calentó más que el invierno", `: ${degC(summer)} contra ${degC(winter)}, en promedio.`],
    );
  }

  const days = avg("warming_max_c");
  const nights = avg("warming_min_c");
  items.push(
    nights > days
      ? ["Las noches se calentaron más que los días", `: las mínimas subieron ${degC(nights)} y las máximas ${degC(days)}.`]
      : ["Los días se calentaron más que las noches", `: las máximas subieron ${degC(days)} y las mínimas ${degC(nights)}.`],
  );

  const hot = [avg("baseline_hot_days"), avg("recent_hot_days")];
  items.push([
    `${hot[1] >= hot[0] ? "Hay más" : "Hay menos"} días de calor`,
    `: en promedio cada ciudad pasó de ${fmt(hot[0], 0)} a ${fmt(hot[1], 0)} días por año con 30 °C o más.`,
  ]);
  const frost = [avg("baseline_frost_days"), avg("recent_frost_days")];
  items.push([`${frost[1] <= frost[0] ? "Hay menos" : "Hay más"} heladas`, `: de ${fmt(frost[0], 0)} a ${fmt(frost[1], 0)} días por año en promedio.`]);

  const nat = nationalSeries();
  if (nat.length) {
    const warmest = nat.reduce((a, b) => (b.anomaly > a.anomaly ? b : a));
    items.push([`El año más cálido fue ${warmest.year}`, `, con ${degC(warmest.anomaly)} sobre el promedio de 1961–1990.`]);
  }

  $("findings").replaceChildren(...items.map(([lead, rest]) => el("li", {}, [el("strong", {}, lead), rest])));
  indexChildren($("findings"));
}

// --- Tabla ---------------------------------------------------------------------------------------

function renderTable() {
  const [r0, r1] = state.data.meta.recent;
  const table = $("summary-table");
  const head = ["Ciudad", "Región", "1961–1990", `${r0}–${r1}`, "Cambio", "Días de 30 °C o más", "Heladas por año"];
  table.tHead.replaceChildren(el("tr", {}, head.map((h) => el("th", { scope: "col" }, h))));
  const arrow = (a, b) => `${fmt(a, 0)} → ${fmt(b, 0)}`;
  const rows = [...state.data.warming].sort((a, b) => b.warming_c - a.warming_c);
  table.tBodies[0].replaceChildren(
    ...rows.map((w) =>
      el("tr", {}, [
        el("td", {}, w.city_name),
        el("td", {}, w.region),
        el("td", {}, `${fmt(w.baseline_temp_mean_c)} °C`),
        el("td", {}, `${fmt(w.recent_temp_mean_c)} °C`),
        el("td", {}, el("strong", {}, degC(w.warming_c))),
        el("td", {}, arrow(w.baseline_hot_days, w.recent_hot_days)),
        el("td", {}, arrow(w.baseline_frost_days, w.recent_frost_days)),
      ]),
    ),
  );
}

// --- Estado en la URL: #ver=heladas&ciudad=salta&anio=1980&tema=dark -----------------------------

function writeHash() {
  const p = new URLSearchParams();
  if (state.metric !== "temperatura") p.set("ver", state.metric);
  if (state.view === "calor") p.set("vista", "calor");
  if (state.selected) p.set("ciudad", state.selected);
  if (state.year !== state.data.meta.last_year) p.set("anio", state.year);
  const theme = document.documentElement.dataset.theme;
  if (theme) p.set("tema", theme);
  const hash = p.toString();
  history.replaceState(null, "", hash ? `#${hash}` : location.pathname + location.search);
}

function applyHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const theme = p.get("tema");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  const ver = p.get("ver");
  if (ver && METRICS[ver]) state.metric = ver;
  if (p.get("vista") === "calor") state.view = "calor";
  const city = p.get("ciudad");
  if (city && hasData(city)) state.selected = city;
  const year = Number(p.get("anio"));
  const { first_year, last_year } = state.data.meta;
  if (year) state.year = Math.min(last_year, Math.max(first_year + 9, year));
}

// --- Inicio ------------------------------------------------------------------------------------

function renderAll() {
  const T = tokens();
  renderNationalStripes(T);
  renderMap(T);
  renderList(T);
  renderDetail(T);
}

async function init() {
  const [data, geo] = await Promise.all([
    fetch("data.json", { cache: "no-cache" }).then((r) => r.json()),
    fetch("argentina.geojson").then((r) => r.json()),
  ]);
  state.data = data;
  state.geo = geo;
  state.year = data.meta.last_year;
  // Arranca mostrando la ciudad que más se calentó.
  state.selected = [...data.warming].sort((a, b) => b.warming_c - a.warming_c)[0]?.city_id ?? null;

  applyHash();
  state.stripesIntro = animating();
  renderOpening();
  renderPicker();
  setupViewToggle();
  setupTimeline();
  renderFindings();
  renderTable();
  renderAll();
  setupReveals();

  const fmtDate = (d) => d.toLocaleDateString("es-AR", { day: "numeric", month: "long", year: "numeric" });
  $("updated").textContent = ` Datos hasta el ${fmtDate(new Date(`${data.meta.data_through}T00:00:00`))}.`;

  let lastWidth = document.documentElement.clientWidth;
  let t;
  new ResizeObserver(() => {
    const w = document.documentElement.clientWidth;
    if (w === lastWidth) return;
    lastWidth = w;
    clearTimeout(t);
    t = setTimeout(renderAll, 120);
  }).observe(document.documentElement);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
}

init().catch((err) => {
  console.error(err);
  document.documentElement.classList.remove("js-anim"); // que el mensaje de error se vea
  $("headline").textContent = "No se pudieron cargar los datos. Recargá la página para intentar de nuevo.";
});
