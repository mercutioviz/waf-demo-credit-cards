/* Live dashboard for the /ops view.

   Plain DOM and EventSource on purpose: this lab has no Node toolchain, and a
   demo screen that needs a build step is a demo screen that breaks in front of
   a prospect. */

const SPARK_POINTS = 12;
const SPARK_W = 104;
const SPARK_H = 26;
const ROW_LIMIT = 25;

const CODE_LABELS = {
    "00": "Approved",
    "05": "Do not honour",
    "14": "Invalid card number",
    "54": "Expired card",
    "82": "Invalid security code",
};

const el = (id) => document.getElementById(id);
const rateHistory = [];

function formatClock(ts) {
    return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

function renderStats(stats) {
    el("hero").textContent = stats.live_cards.length.toLocaleString();
    el("total").textContent = stats.total.toLocaleString();
    el("declined").textContent = stats.declined.toLocaleString();
    el("rate").textContent = stats.rate.toLocaleString();
    el("ips").textContent = stats.unique_ips.toLocaleString();
    el("bins").textContent = stats.unique_bins.toLocaleString();
    el("elapsed").textContent = `${Math.round(stats.elapsed)}s elapsed`;
    el("sessions").textContent =
        `${stats.unique_sessions.toLocaleString()} session${stats.unique_sessions === 1 ? "" : "s"}`;

    const codes = Object.entries(stats.by_code)
        .filter(([code]) => code !== "00")
        .sort((a, b) => b[1] - a[1])
        .slice(0, 2)
        .map(([code, count]) => `${code} × ${count.toLocaleString()}`);
    el("decline-codes").innerHTML = codes.length ? codes.join(" · ") : "&mdash;";

    renderLiveCards(stats.live_cards);
}

function renderLiveCards(cards) {
    const list = el("live-cards");
    el("live-empty").style.display = cards.length ? "none" : "block";
    list.replaceChildren(
        ...cards.slice(-12).reverse().map((card) => {
            const li = document.createElement("li");
            li.textContent = card;
            return li;
        })
    );
}

function buildRow(attempt) {
    const tr = document.createElement("tr");
    if (attempt.approved) tr.className = "hit";

    const outcome = document.createElement("span");
    outcome.className = `outcome ${attempt.approved ? "approved" : "declined"}`;
    outcome.textContent = attempt.approved ? "APPROVED" : "DECLINED";

    const cells = [
        formatClock(attempt.ts),
        attempt.pan,
        attempt.bin,
        outcome,
        `${attempt.code} ${CODE_LABELS[attempt.code] || ""}`.trim(),
        attempt.ip,
        attempt.ua,
        attempt.session || "—",
    ];

    cells.forEach((value, index) => {
        const td = document.createElement("td");
        if (index === 1 || index === 2) td.className = "mono";
        if (value instanceof Node) td.appendChild(value);
        else td.textContent = value;
        tr.appendChild(td);
    });
    return tr;
}

function prependAttempt(attempt) {
    const body = el("attempts");
    el("attempts-empty").style.display = "none";
    body.prepend(buildRow(attempt));
    while (body.childElementCount > ROW_LIMIT) body.lastElementChild.remove();
}

function renderAttempts(attempts) {
    const body = el("attempts");
    el("attempts-empty").style.display = attempts.length ? "none" : "block";
    body.replaceChildren(...attempts.slice(0, ROW_LIMIT).map(buildRow));
}

/* 12-point sparkline: the series sits in the de-emphasis hue and only the
   current sample wears the accent, so the eye lands on "now". */
function renderSparkline() {
    const svg = el("spark");
    if (rateHistory.length < 2) {
        svg.replaceChildren();
        return;
    }
    const peak = Math.max(...rateHistory, 1);
    const step = SPARK_W / (SPARK_POINTS - 1);
    const points = rateHistory.map((value, index) => {
        const x = index * step;
        const y = SPARK_H - 3 - (value / peak) * (SPARK_H - 6);
        return [x, y];
    });

    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "#898781");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-linejoin", "round");
    line.setAttribute("stroke-linecap", "round");

    const [cx, cy] = points[points.length - 1];
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", cx.toFixed(1));
    dot.setAttribute("cy", cy.toFixed(1));
    dot.setAttribute("r", "2.5");
    dot.setAttribute("fill", "#E8660A");

    svg.replaceChildren(line, dot);
}

async function load() {
    const response = await fetch("/ops/snapshot");
    const data = await response.json();
    renderStats(data.stats);
    renderAttempts(data.recent);
}

function connect() {
    const source = new EventSource("/ops/stream");
    source.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "reset") {
            renderStats(payload.stats);
            renderAttempts([]);
            rateHistory.length = 0;
            renderSparkline();
            return;
        }
        renderStats(payload.stats);
        prependAttempt(payload.attempt);
    };
    // EventSource reconnects on its own; this only surfaces a hard failure in
    // the console rather than letting the dashboard look merely idle.
    source.onerror = () => console.warn("ops stream interrupted; retrying");
}

el("reset").addEventListener("click", async () => {
    await fetch("/ops/reset", { method: "POST" });
});

setInterval(async () => {
    const response = await fetch("/ops/snapshot");
    const data = await response.json();
    rateHistory.push(data.stats.rate);
    while (rateHistory.length > SPARK_POINTS) rateHistory.shift();
    renderSparkline();
}, 1000);

load();
connect();
