const KEY_STORAGE = "orca-lite-api-key";

function apiKey() { return localStorage.getItem(KEY_STORAGE) || ""; }
function setApiKey(k) { localStorage.setItem(KEY_STORAGE, k); }

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (apiKey()) headers["Authorization"] = `Bearer ${apiKey()}`;
  const r = await fetch(path, { ...opts, headers });
  if (!r.ok) {
    const body = await r.json().catch(() => ({ error: { message: r.statusText } }));
    throw new Error(body.error?.message || r.statusText);
  }
  if (r.status === 204) return null;
  return r.json();
}

// ── auth gate ─────────────────────────────────────────────
async function checkAuth() {
  if (!apiKey()) return false;
  try {
    await api("/v1/keys");
    return true;
  } catch {
    return false;
  }
}

async function showApp() {
  document.getElementById("auth-gate").hidden = true;
  document.getElementById("tabs").hidden = false;
  document.getElementById("panels").hidden = false;
  await Promise.all([loadProviders(), loadRouting(), loadAnalytics(), loadKeys()]);
}

document.getElementById("api-key-save").addEventListener("click", async () => {
  const v = document.getElementById("api-key-input").value.trim();
  setApiKey(v);
  const ok = await checkAuth();
  const status = document.getElementById("auth-status");
  if (ok) {
    status.textContent = "Authenticated.";
    status.classList.add("ok");
    showApp();
  } else {
    status.textContent = "Invalid key.";
    status.classList.remove("ok");
  }
});

// ── tabs ──────────────────────────────────────────────────
document.querySelectorAll("nav#tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav#tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
  });
});

// ── providers ─────────────────────────────────────────────
async function loadProviders() {
  const data = await api("/v1/providers");
  const tbody = document.querySelector("#providers-table tbody");
  tbody.innerHTML = "";
  data.providers.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.provider}</td>
      <td><code>${p.key_prefix}</code></td>
      <td>${p.is_enabled ? "✓" : "✗"}</td>
      <td><button data-prov="${p.provider}" class="del-prov">Delete</button></td>
    `;
    tbody.appendChild(tr);
  });
  document.querySelectorAll(".del-prov").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/v1/providers/${b.dataset.prov}`, { method: "DELETE" });
      loadProviders();
    })
  );
}

document.getElementById("provider-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const provider = document.getElementById("provider-name").value;
  const apiKeyVal = document.getElementById("provider-key").value.trim();
  if (!apiKeyVal) return;
  await api(`/v1/providers/${provider}`, {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKeyVal }),
  });
  document.getElementById("provider-key").value = "";
  loadProviders();
});

// ── routing ───────────────────────────────────────────────
async function loadRouting() {
  const r = await api("/v1/routing");
  document.getElementById("routing-strategy").value = r.strategy;
}

document.getElementById("routing-save").addEventListener("click", async () => {
  const strategy = document.getElementById("routing-strategy").value;
  await api("/v1/routing", { method: "PUT", body: JSON.stringify({ strategy }) });
  document.getElementById("routing-status").textContent = "Saved.";
  setTimeout(() => (document.getElementById("routing-status").textContent = ""), 2000);
});

// ── analytics ─────────────────────────────────────────────
async function loadAnalytics() {
  const [recent, spend] = await Promise.all([
    api("/v1/analytics/recent?limit=50"),
    api("/v1/analytics/spend?days=7"),
  ]);
  const usd = (spend.total_microcents / 1_000_000).toFixed(4);
  document.getElementById("spend-summary").textContent =
    `Last 7 days: $${usd} across ${spend.by_model.reduce((a, m) => a + m.request_count, 0)} requests`;

  const tbody = document.querySelector("#recent-table tbody");
  tbody.innerHTML = "";
  recent.items.forEach((it) => {
    const tr = document.createElement("tr");
    const when = it.created_at ? new Date(it.created_at).toLocaleString() : "—";
    tr.innerHTML = `
      <td>${when}</td>
      <td><code>${it.model_resolved}</code></td>
      <td>${it.provider}</td>
      <td>${it.input_tokens} / ${it.output_tokens}</td>
      <td>${it.latency_ms} ms</td>
      <td>${it.status_code}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ── keys ──────────────────────────────────────────────────
async function loadKeys() {
  const data = await api("/v1/keys");
  const tbody = document.querySelector("#keys-table tbody");
  tbody.innerHTML = "";
  data.keys.forEach((k) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${k.name}</td>
      <td><code>${k.key_prefix}</code></td>
      <td>${k.is_active ? "✓" : "✗"}</td>
      <td>${k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "—"}</td>
      <td>${k.is_active ? `<button data-id="${k.id}" class="rev-key">Revoke</button>` : ""}</td>
    `;
    tbody.appendChild(tr);
  });
  document.querySelectorAll(".rev-key").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/v1/keys/${b.dataset.id}`, { method: "DELETE" });
      loadKeys();
    })
  );
}

document.getElementById("key-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("key-name").value.trim();
  if (!name) return;
  const r = await api("/v1/keys", { method: "POST", body: JSON.stringify({ name }) });
  const display = document.getElementById("new-key-display");
  display.textContent = `Save this key — it won't be shown again: ${r.api_key}`;
  display.classList.add("shown");
  document.getElementById("key-name").value = "";
  loadKeys();
});

// ── boot ──────────────────────────────────────────────────
checkAuth().then((ok) => {
  if (ok) showApp();
});
