/* ==========================================================================
   OrcaRouter Lite — dashboard
   Vanilla JS, no build step. State -> render. Keyboard-first DX.
   ========================================================================== */

const KEY_STORAGE = "orca-lite-api-key";
const ONBOARDING_KEY = "orca-lite-getting-started-dismissed";
const LOCALE_KEY = "orca-lite-locale";
const SUPPORTED_LOCALES = ["en", "zh", "hi", "es", "pt", "ru", "ja", "de", "fr", "it", "ar", "ko"];
const LOCALE_LABELS = { en: "English", zh: "中文", hi: "हिन्दी", es: "Español", pt: "Português", ru: "Русский", ja: "日本語", de: "Deutsch", fr: "Français", it: "Italiano", ar: "العربية", ko: "한국어" };
const I18N = {
  en: {
    // Full UI strings. `zh` below is the only other locale kept fully in
    // sync; the remaining 10 locales intentionally ship the small base set
    // and fall back to `I18N.en` via `t()` for everything else.
    "auth.tagline":"Open Source. Single Tenant.","auth.welcome":"Welcome back","auth.subtitle":"Paste the sk-orca-* key printed in your server logs on first run. Stored only in this browser via localStorage.","auth.api_key":"API key","auth.continue":"Continue",
    "nav.search":"Search","nav.overview":"Overview","nav.providers":"Providers","nav.routing":"Routing","nav.analytics":"Analytics",
    "nav.api_keys":"API keys","nav.help_docs":"Help & docs","nav.sign_out":"Sign out","status.connected":"Connected","status.disconnected":"Disconnected",
    "auth.checking":"Checking…","auth.welcome_aboard":"Welcome aboard.","auth.key_invalid":"That key didn't work. Double-check the prefix sk-orca-…","tab.overview.title":"Overview","tab.overview.sub":"Your single-tenant LLM router at a glance.",
    "tab.providers.title":"Provider keys","tab.providers.sub":"BYOK — encrypted at rest, used to call upstream LLMs.","tab.routing.title":"Routing","tab.routing.sub":"How model='auto' picks the right model for each request.","tab.analytics.title":"Analytics",
    "tab.analytics.sub":"Local-only spend, latency and request history.","tab.keys.title":"API keys","tab.keys.sub":"Tokens that authenticate clients against this Lite workspace.","nav.quality":"Quality","tab.quality.title":"Quality scores",
    "tab.quality.sub":"Real benchmark scores for the quality routing strategy. Pulls from Artificial Analysis.","providers.base_url":"Base URL","providers.optional":"optional","providers.endpoint":"Endpoint","providers.endpoint_default":"default",
    "providers.rescan":"Rescan","common.request_failed":"Request failed","common.copy_ok":"Copied to clipboard","common.copy_blocked":"Could not copy — your browser blocked it","common.remove":"Remove",
    "common.enabled":"Enabled","common.disabled":"Disabled","common.active":"Active","common.revoked":"Revoked","common.revoke":"Revoke",
    "common.never":"Never","common.reset":"Reset","common.set":"Set","common.not_configured":"Not configured","common.no_matches":"No matches",
    "time.seconds_ago":"{sec}s ago","time.minutes_ago":"{min}m ago","time.hours_ago":"{hrs}h ago","providers.quick_add":"Quick-add:","providers.env_title":"Set via .env / environment variable. Edit the env file and restart to change.",
    "providers.endpoint_default_title":"Vendor default endpoint — models come from the built-in catalog.","providers.rescan_title":"Re-list models from this endpoint","providers.env_managed_title":"Remove the OPENAI_API_KEY (or equivalent) from .env and restart the server.","providers.remove_confirm":"Remove the {prov} key? Requests routed to {prov} will start failing.","providers.removed":"Removed {prov}",
    "providers.chip_env_title":"{label} is set via .env. Click to override with a custom key (writes a DB row that takes precedence).","providers.env_override":"(env, override)","providers.name_required":"Provider name is required","providers.key_empty":"API key cannot be empty","providers.saved":"Saved {provider} key",
    "providers.found_model":"Found {count} model on {prov}","providers.found_models":"Found {count} models on {prov}","providers.load_err":"Couldn't load providers: {msg}","routing.load_err":"Couldn't load routing: {msg}","routing.strategy_saved":"Routing strategy: {val}",
    "analytics.load_err":"Couldn't load analytics: {msg}","analytics.no_spend":"No spend data yet for this window.","analytics.no_spend_hint":"Send a request through <code>/v1/chat/completions</code> to see your costs here.","analytics.no_data_window":"No data yet for this window.","analytics.spend_summary":"Last <strong>{days}d</strong> · <strong>{cost}</strong> across <strong>{n}</strong> requests",
    "analytics.chart_tooltip":"{n} requests, {cost}","analytics.req":"req","analytics.trace_tip":"Click to copy trace ID","analytics.no_requests":"No requests yet.","analytics.no_requests_hint":"Once you send your first <code>chat.completions</code> call, it'll show up here.",
    "keys.load_err":"Couldn't load keys: {msg}","keys.empty":"No keys yet. Create one above.","keys.revoke_confirm":"Revoke \\\\\\\"{name}\\\\\\\"? Any client using it will start getting 401 immediately.","keys.revoked":"Revoked {name}","keys.name_required":"Give the key a name first",
    "keys.created":"Created {name}","hosted.no_history":"No comparable request history yet — once traffic flows, this card will show how much routing through hosted-auto would save.","hosted.savings_detected":"Up to <strong>{amount}</strong> additional savings detected ({pct}% of comparable-traffic spend) by routing through hosted-auto on the cheapest catalog model per request.","hosted.already_optimal":"Already optimal — your current routing matches the cheapest hosted-auto pick on every comparable request.","hosted.env_active":"Active via environment variable (<code>ORCAROUTER_API_KEY</code>). Every catalog model is reachable. To disable, unset the env var and restart.",
    "hosted.db_active":"Active via dashboard. Every catalog model is reachable.","hosted.activate_ok":"Hosted fallback activated — every model is now reachable","hosted.disable_confirm":"Disable hosted fallback? Requests for models without a local key will start failing.","hosted.disabled":"Hosted fallback disabled","hosted.paste_hint":"Paste your sk-orca-* key from orcarouter.ai/console/token",
    "hosted.clipboard_empty":"Clipboard is empty — copy your sk-orca-* key first","hosted.paste_blocked":"Your browser blocked clipboard access — paste with Ctrl+V","quality.load_err":"Couldn't load quality scores: {msg}","quality.source_live":"live","quality.source_stale_aa":"stale (AA unreachable)",
    "quality.source_stale_db":"stale (DB snapshot)","quality.source_error":"error","quality.source_no_key":"no API key","quality.source_unknown":"unknown","quality.status_fmt":"matched <strong>{matched}</strong> of <strong>{total}</strong> AA models to your catalog · <strong>{overrides}</strong> manual override",
    "quality.empty":"No models in catalog.","quality.aa_title":"Artificial Analysis Intelligence Index","quality.tps_title":"Output tokens per second (AA median, max across reasoning variants)","quality.ttft_title":"Time to first token in seconds (AA median, min across variants — non-reasoning fast mode)","quality.reset_title":"Revert to AA score",
    "quality.unscored":"unscored","quality.deployable":"deployable","quality.no_key":"no key","quality.no_deployable":"No deployable model satisfies the current capability requirements. Configure a provider key on the Providers page.","quality.score_fmt":"score {score}",
    "quality.falls_back_fmt":"→ falls back to: {list}","quality.strategy_prefix":"strategy:","quality.scoring_prefix":"scoring:","quality.prompt_score":"Set manual quality score for {model} (0-100):","quality.prompt_aa_hint":"AA score is currently: {score}",
    "quality.prompt_note":"Optional note (why are you overriding?):","quality.score_range":"Score must be a number between 0 and 100","quality.override_set":"Override set for {model}","quality.reset_confirm":"Reset {model} to its AA score?","quality.reset_done":"Reset {model}",
    "quality.refreshed":"Refreshed scores from Artificial Analysis","quality.refresh_failed":"Refresh failed: {msg}","overview.across_reqs":"across {n} requests","overview.vs_gpt4o_off":"vs always-GPT-4o ({pct}% off)","overview.vs_gpt4o_base":"vs always-GPT-4o baseline",
    "overview.already_optimal":"already optimal","overview.provider_1":"{n} provider configured","overview.provider_n":"{n} providers configured","palette.go_overview":"Go to Overview","palette.go_providers":"Go to Providers",
    "palette.go_routing":"Go to Routing","palette.go_analytics":"Go to Analytics","palette.go_keys":"Go to API keys","palette.copy_base":"Copy base URL","palette.copy_snippet":"Copy quickstart snippet",
    "palette.open_help":"Open help & docs","palette.open_docs":"Open docs.orcarouter.ai","palette.open_site":"Open orcarouter.ai","palette.get_hosted_key":"Get hosted API key (orcarouter.ai/console/token)","palette.logout":"Sign out (forget API key)",
    "palette.meta_tab":"Tab","palette.meta_action":"Action","palette.meta_help":"Help","palette.meta_link":"Link","auth.signed_out":"Signed out — your key is forgotten on this device",
    "unreachable.per_1m":"per 1M","unreachable.provider_prefix":"Provider:","ui.auth.find_key":"Where do I find my key?","ui.auth.run_li":"Run <code>docker compose up</code> (or <code>uvicorn app.main:app</code>).","ui.auth.first_run_li":"On first start, the server prints:<br><code class=\"code-block\">✓ orcarouter-lite ready. API key: sk-orca-...</code>",
    "ui.auth.copy_paste":"Copy that string and paste it above.","ui.auth.reset_p":"Lost it? Reset the workspace by deleting <code>orcarouter.db</code> (and any <code>data/</code> volume) and restarting.","ui.common.language":"Language","ui.common.copy_base_tip":"Copy your base URL","ui.common.logout_tip":"Forget API key (this device)",
    "ui.overview.spend_tip":"Sum of all upstream costs over the last 7 days","ui.overview.spend_label":"Spend (7d)","ui.overview.savings_tip":"Top: vs GPT-4o for the same traffic. Bottom: extra savings hosted-auto could unlock by reaching cheaper models you don't have keys for.","ui.overview.routing_savings":"Routing savings","ui.overview.vs_hosted_auto":"vs hosted-auto",
    "ui.overview.latency_tip":"True median latency across the most recent requests (raw samples, not averaged)","ui.overview.p50_label":"p50 latency","ui.overview.models_tip":"Models discovered from your configured provider keys + the catalog","ui.overview.models_label":"Models available","ui.overview.quick_start":"Quick start",
    "ui.overview.quick_sub":"You're up — point any OpenAI SDK at your base URL.","ui.common.copy_snippet_tip":"Copy snippet","ui.overview.auto_hint":"Use <code>model=\"auto\"</code> to let the router pick the cheapest capable model.","ui.overview.recent_title":"Recent activity","ui.overview.recent_sub":"Last 5 requests routed through this server.",
    "ui.common.view_all":"View all","ui.hosted.title":"Hosted fallback <span class=\"pill\" id=\"hosted-status-pill\">Not configured</span>","ui.hosted.card_sub":"One key, every model. Standard fallback for any model you don't have a local key for. Free <strong>$5</strong> trial credit on sign-up — no credit card.","ui.hosted.get_key_on_site":"Get your key on orcarouter.ai","ui.hosted.step1_hint":"Opens the token console in a new tab — copy your <code>sk-orca-*</code> key there.",
    "ui.hosted.register":"No account yet? Sign up for free $5 credit","ui.hosted.step2_hint":"Come back here, paste the key and activate.","ui.hosted.api_key_label":"Hosted API key","ui.hosted.paste_tip":"Paste from clipboard","ui.common.paste":"Paste",
    "ui.hosted.activate":"Activate fallback","ui.hosted.unreachable_intro":"Models you can't reach today — hosted unlocks all of them:","ui.hosted.disable_tip":"Disable hosted fallback","ui.hosted.remove_key":"Remove key","ui.hosted.onboarding_title":"New here? Get fully set up in 2 minutes",
    "ui.hosted.onb1":"<span class=\"check\"></span>Add at least one <a href=\"#\" data-go-tab=\"providers\">provider key</a>","ui.hosted.onb2":"<span class=\"check\"></span>Pick a <a href=\"#\" data-go-tab=\"routing\">routing strategy</a>","ui.hosted.onb3":"<span class=\"check\"></span>Send your first request (it'll appear in <a href=\"#\" data-go-tab=\"analytics\">analytics</a>)","ui.hosted.title_prov":"Hosted fallback <span class=\"pill\" id=\"providers-hosted-pill\">Not configured</span>","ui.hosted.prov_sub":"Cover the long tail without per-provider sign-ups. Free <strong>$5</strong> credit, billed at cost after.",
    "ui.hosted.get_key":"Get your key","ui.providers.title":"Provider keys <span class=\"pill\">BYOK</span>","ui.providers.sub":"Encrypted at rest with AES-256-GCM. Env vars override DB rows for the same provider.","ui.providers.name":"Provider","ui.providers.api_key":"API key",
    "ui.common.save_key":"Save key","ui.common.provider":"Provider","ui.common.prefix":"Prefix","ui.common.status":"Status","ui.providers.empty_title":"No provider keys yet",
    "ui.providers.empty_sub":"Add at least one to start routing real traffic. Pick a provider above or click a quick-add chip.","ui.routing.title":"Routing strategy","ui.routing.sub":"How the router picks between candidate models when you send <code>model=\"auto\"</code>.","ui.routing.balanced":"Balanced","ui.routing.balanced_desc":"50/50 weighted blend of AA quality & cost. The sane default for most teams.",
    "ui.routing.recommended":"Recommended","ui.routing.cheapest":"Cheapest","ui.routing.cheapest_desc":"Lowest per-token cost that still meets the request's capabilities.","ui.routing.fastest":"Fastest","ui.routing.fastest_desc":"Highest throughput + lowest first-token latency, from Artificial Analysis benchmarks. Great for chat UIs.",
    "ui.routing.quality":"Quality","ui.routing.quality_desc":"Prefers frontier models. Best for hard reasoning tasks.","ui.routing.pick_hint":"Pick a card to switch strategy. Saved automatically.","ui.routing.how_title":"How <code>model=\"auto\"</code> works","ui.routing.how_sub":"Three filters, applied in order.",
    "ui.routing.cap_filter":"Capability filter.","ui.routing.cap_desc":"The router inspects your request — is there an image? a tool definition? <code>response_format=json</code>? — and drops models that can't handle it.","ui.routing.prov_filter":"Provider filter.","ui.routing.prov_desc":"Only models whose provider you've configured (or that hosted upstream covers) survive.","ui.routing.strat_rank":"Strategy ranking.",
    "ui.routing.strat_rank_desc":"The remaining candidates are scored by your chosen strategy above. The winner is called.","ui.routing.resolved_hint":"The chosen model comes back to your client in the <code>x-orca-resolved-model</code> response header. The strategy in effect is echoed as <code>x-orca-routing-strategy</code>.","ui.routing.map_summary":"How each strategy maps to LiteLLM Router","ui.routing.map_strategy":"Strategy","ui.routing.map_litellm":"litellm <code>routing_strategy</code>",
    "ui.routing.map_picks":"<code>model=\"auto\"</code> picks","ui.routing.we_rank":"<code>None</code> (we rank ourselves)","ui.routing.map_balanced_desc":"50/50 normalized AA quality & inverted cost; strict two-axis coverage","ui.routing.map_cheapest_desc":"cheapest capable (blended 0.3 input + 0.7 output cost)","ui.routing.map_fastest_desc":"50/50 normalized AA TPS & inverted TTFT; strict two-axis coverage",
    "ui.routing.map_quality_desc":"highest AA Intelligence Index (or manual override); unscored models rank below scored","ui.routing.map_foot":"The strategy controls two things: which model <code>model=\"auto\"</code> resolves to, and how LiteLLM Router picks between deployments that serve the same model (e.g. local OpenAI key + hosted upstream).","ui.analytics.spend_title":"Spend by model","ui.analytics.latency_title":"Latency by provider","ui.analytics.latency_sub":"p50 and p99 — sourced from local request logs.",
    "ui.analytics.requests":"Requests","ui.analytics.recent_title":"Recent requests","ui.analytics.recent_sub":"Newest first. Click a row to copy its trace ID.","ui.analytics.when":"When","ui.common.model":"Model",
    "ui.analytics.tokens":"Tokens (in / out)","ui.analytics.latency":"Latency","ui.analytics.no_traffic":"No traffic yet","ui.analytics.no_traffic_sub":"Once you start sending requests, they'll appear here in real time.","ui.keys.intro":"Each key authenticates against this Lite workspace. Plaintext is shown <strong>once</strong> on creation.",
    "ui.keys.name":"Name","ui.keys.create":"Create key","ui.keys.save_warn":"Save this key — it won't be shown again.","ui.common.copy_tip":"Copy","ui.keys.last_used":"Last used",
    "ui.quality.setup_title":"Set up quality scoring","ui.quality.setup_p1":"Strategy <code>quality</code> currently picks the most expensive model — a proxy that broke when newer flagships (Claude Opus 4.7, GPT-5.x) shipped at lower prices than older ones. Set an Artificial Analysis API key to route by real benchmark scores instead.","ui.quality.setup_li1":"Sign up free at <a href=\"https://artificialanalysis.ai\" target=\"_blank\" rel=\"noopener\">artificialanalysis.ai</a> and generate an API key (free tier: 1,000 req/day, plenty for 1h-cached usage).","ui.quality.setup_li2":"Add it to your <code>.env</code> as <code>ARTIFICIAL_ANALYSIS_API_KEY=...</code> and restart.","ui.quality.setup_li3":"Reload this page — scores will appear automatically.",
    "ui.quality.setup_foot":"Without a key, <code>quality</code> falls back to the legacy cost-based behavior. <code>cheapest</code> / <code>balanced</code> / <code>fastest</code> are unaffected. You can still set <strong>manual overrides</strong> on individual models in the table below — those work without an AA key and take precedence when present.","ui.quality.refresh":"Refresh from AA","ui.quality.preview_title":"Right now, <code>model=\"auto\"</code> would resolve to:","ui.quality.models_title":"Models","ui.quality.models_sub":"Edit a row's <strong>Manual</strong> column to override the AA score for routing decisions. Manual values win over AA. Use this when your own evals disagree, or when AA hasn't scored a model yet.",
    "ui.quality.manual":"Manual","ui.quality.effective":"Effective","ui.quality.tps_th_title":"Output tokens per second (Artificial Analysis median, max across reasoning variants). — when AA hasn't indexed this model.","ui.quality.ttft_th_title":"Time to first token in seconds (Artificial Analysis median, min across reasoning variants — the model's non-reasoning fast mode). — when AA hasn't indexed this model.","ui.quality.blended":"$/M blended",
    "ui.quality.powered":"Powered by <a href=\"https://artificialanalysis.ai\" target=\"_blank\" rel=\"noopener\">Artificial Analysis</a> — Intelligence Index aggregates MMLU-Pro, GPQA, MATH, HumanEval, and other benchmarks. Attribution required.","ui.help.what_title":"What is OrcaRouter Lite?","ui.help.what_body":"A self-hosted, OpenAI-compatible LLM router. Bring your own provider keys (BYOK), point any OpenAI SDK at the local base URL, and the router picks the cheapest capable model for each request — with optional fallback to hosted <a href=\"https://api.orcarouter.ai\" target=\"_blank\" rel=\"noreferrer\">api.orcarouter.ai</a>.","ui.help.quick_title":"60-second quickstart","ui.help.qs1":"Add a provider key under <a href=\"#\" data-go-tab=\"providers\">Providers</a> (or set <code>OPENAI_API_KEY</code> in your env).",
    "ui.help.qs2":"Optionally choose a <a href=\"#\" data-go-tab=\"routing\">routing strategy</a>.","ui.help.qs3":"Use this URL as your OpenAI <code>base_url</code>: <code id=\"help-base-url\">http://localhost:8000/v1</code>","ui.help.qs4":"Use the <code>sk-orca-*</code> key you signed in with as the API key.","ui.help.kb_title":"Keyboard shortcuts","ui.help.kb_tabs":"Switch tabs",
    "ui.help.kb_palette":"Command palette","ui.help.kb_help":"Toggle this help","ui.help.kb_close":"Close drawers / palette","ui.help.further_title":"Going further",
  },
  zh: { "auth.tagline":"开源。单租户。", "auth.welcome":"欢迎回来", "auth.subtitle":"粘贴首次运行时服务器日志中的 sk-orca-* 密钥。仅保存在此浏览器 localStorage。", "auth.api_key":"API 密钥", "auth.continue":"继续", "nav.search":"搜索", "nav.overview":"概览", "nav.providers":"供应商", "nav.routing":"路由", "nav.analytics":"分析", "nav.api_keys":"API 密钥", "nav.help_docs":"帮助与文档", "nav.sign_out":"退出登录", "status.connected":"已连接", "status.disconnected":"已断开", "auth.checking":"正在检查…", "auth.welcome_aboard":"欢迎使用。", "auth.key_invalid":"该密钥无效，请检查前缀 sk-orca-…", "tab.overview.title":"概览", "tab.overview.sub":"一览你的单租户 LLM 路由器。", "tab.providers.title":"供应商密钥", "tab.providers.sub":"BYOK — 静态加密存储，用于调用上游 LLM。", "tab.routing.title":"路由", "tab.routing.sub":"model='auto' 如何为每个请求选择合适模型。", "tab.analytics.title":"分析", "tab.analytics.sub":"仅本地的花费、延迟和请求历史。", "tab.keys.title":"API 密钥", "tab.keys.sub":"用于在此 Lite 工作区中验证客户端的令牌。", "nav.quality":"质量", "tab.quality.title":"质量分数", "tab.quality.sub":"真实 benchmark 分数驱动 quality 路由策略,数据来自 Artificial Analysis。", "providers.base_url":"接口地址", "providers.optional":"可选", "providers.endpoint":"端点", "providers.endpoint_default":"默认", "providers.rescan":"重新扫描", "common.request_failed":"请求失败", "common.copy_ok":"已复制到剪贴板", "common.copy_blocked":"复制失败 — 浏览器已阻止", "common.remove":"删除", "common.enabled":"已启用", "common.disabled":"已禁用", "common.active":"生效中", "common.revoked":"已撤销", "common.revoke":"撤销", "common.never":"从未", "common.reset":"重置", "common.set":"设置", "common.not_configured":"未配置", "common.no_matches":"无匹配", "time.seconds_ago":"{sec} 秒前", "time.minutes_ago":"{min} 分钟前", "time.hours_ago":"{hrs} 小时前", "providers.quick_add":"快捷添加：", "providers.env_title":"通过 .env / 环境变量设置；修改 env 文件并重启后生效。", "providers.endpoint_default_title":"厂商默认端点 — 模型来自内置目录。", "providers.rescan_title":"重新从此端点拉取模型", "providers.env_managed_title":"从 .env 中移除 OPENAI_API_KEY（或对应变量）并重启服务器。", "providers.remove_confirm":"删除 {prov} 的密钥？路由到 {prov} 的请求将开始失败。", "providers.removed":"已删除 {prov}", "providers.chip_env_title":"{label} 通过 .env 设置。点击可用自定义密钥覆盖（将写入优先的数据库记录）。", "providers.env_override":"(env，可覆盖)", "providers.name_required":"必须填写供应商名称", "providers.key_empty":"API 密钥不能为空", "providers.saved":"已保存 {provider} 的密钥", "providers.found_model":"在 {prov} 上发现 {count} 个模型", "providers.found_models":"在 {prov} 上发现 {count} 个模型", "providers.load_err":"无法加载供应商：{msg}", "routing.load_err":"无法加载路由：{msg}", "routing.strategy_saved":"路由策略：{val}", "analytics.load_err":"无法加载分析：{msg}", "analytics.no_spend":"此时间窗口暂无花费数据。", "analytics.no_spend_hint":"通过 <code>/v1/chat/completions</code> 发送请求后，可在此查看花费。", "analytics.no_data_window":"此时间窗口暂无数据。", "analytics.spend_summary":"最近 <strong>{days} 天</strong> · 共 <strong>{n}</strong> 次请求，花费 <strong>{cost}</strong>", "analytics.chart_tooltip":"{n} 次请求，{cost}", "analytics.req":"次", "analytics.trace_tip":"点击复制 Trace ID", "analytics.no_requests":"暂无请求。", "analytics.no_requests_hint":"发送首次 <code>chat.completions</code> 调用后，它会显示在这里。", "keys.load_err":"无法加载密钥：{msg}", "keys.empty":"暂无密钥。请在上方创建。", "keys.revoke_confirm":"撤销“{name}”？使用它的客户端将立即开始收到 401。", "keys.revoked":"已撤销 {name}", "keys.name_required":"请先为密钥命名", "keys.created":"已创建 {name}", "hosted.no_history":"暂无足够的可比请求历史 — 产生流量后，此卡片将显示通过 hosted-auto 路由可节省的金额。", "hosted.savings_detected":"每个请求经 hosted-auto 路由到目录中最便宜的模型，预计还可节省最多 <strong>{amount}</strong>（占可比流量花费的 {pct}%）。", "hosted.already_optimal":"已达最优 — 每个可比请求的当前路由均已匹配最便宜的 hosted-auto 选择。", "hosted.env_active":"通过环境变量生效（<code>ORCAROUTER_API_KEY</code>）。目录中所有模型均可达；如需停用，请取消该环境变量并重启。", "hosted.db_active":"已通过面板启用。目录中所有模型均可达。", "hosted.activate_ok":"已启用 Hosted 回退 — 所有模型现在均可达", "hosted.disable_confirm":"停用 Hosted 回退？没有本地密钥的模型请求将开始失败。", "hosted.disabled":"已停用 Hosted 回退", "hosted.paste_hint":"请粘贴来自 orcarouter.ai/console/token 的 sk-orca-* 密钥", "hosted.clipboard_empty":"剪贴板为空 — 请先复制 sk-orca-* 密钥", "hosted.paste_blocked":"浏览器阻止了剪贴板访问 — 请用 Ctrl+V 粘贴", "quality.load_err":"无法加载质量分数：{msg}", "quality.source_live":"实时", "quality.source_stale_aa":"过期（AA 不可达）", "quality.source_stale_db":"过期（DB 快照）", "quality.source_error":"错误", "quality.source_no_key":"无 API 密钥", "quality.source_unknown":"未知", "quality.status_fmt":"目录中 <strong>{total}</strong> 个 AA 模型已匹配 <strong>{matched}</strong> 个 · <strong>{overrides}</strong> 个手动覆盖", "quality.empty":"目录中暂无模型。", "quality.aa_title":"Artificial Analysis 智能指数", "quality.tps_title":"每秒输出 Token（AA 中位数，推理变体取最大）", "quality.ttft_title":"首 Token 时间（秒，AA 中位数，各变体取最小 — 非推理快速模式）", "quality.reset_title":"还原为 AA 分数", "quality.unscored":"未评分", "quality.deployable":"可部署", "quality.no_key":"无密钥", "quality.no_deployable":"没有可部署模型满足当前能力要求。请在“供应商”页配置供应商密钥。", "quality.score_fmt":"分数 {score}", "quality.falls_back_fmt":"→ 回退至：{list}", "quality.strategy_prefix":"策略：", "quality.scoring_prefix":"评分：", "quality.prompt_score":"为 {model} 设置手动质量分数（0-100）：", "quality.prompt_aa_hint":"AA 分数当前为：{score}", "quality.prompt_note":"可选备注（覆盖原因）：", "quality.score_range":"分数必须是 0 到 100 之间的数字", "quality.override_set":"已为 {model} 设置覆盖", "quality.reset_confirm":"将 {model} 重置为 AA 分数？", "quality.reset_done":"已重置 {model}", "quality.refreshed":"已从 Artificial Analysis 刷新分数", "quality.refresh_failed":"刷新失败：{msg}", "overview.across_reqs":"共 {n} 次请求", "overview.vs_gpt4o_off":"对比始终使用 GPT-4o（省 {pct}%）", "overview.vs_gpt4o_base":"对比始终使用 GPT-4o 基线", "overview.already_optimal":"已达最优", "overview.provider_1":"{n} 个供应商已配置", "overview.provider_n":"{n} 个供应商已配置", "palette.go_overview":"前往概览", "palette.go_providers":"前往供应商", "palette.go_routing":"前往路由", "palette.go_analytics":"前往分析", "palette.go_keys":"前往 API 密钥", "palette.copy_base":"复制 Base URL", "palette.copy_snippet":"复制快速入门代码", "palette.open_help":"打开帮助与文档", "palette.open_docs":"打开 docs.orcarouter.ai", "palette.open_site":"打开 orcarouter.ai", "palette.get_hosted_key":"获取 Hosted API 密钥（orcarouter.ai/console/token）", "palette.logout":"退出登录（清除 API 密钥）", "palette.meta_tab":"标签页", "palette.meta_action":"操作", "palette.meta_help":"帮助", "palette.meta_link":"链接", "auth.signed_out":"已退出登录 — 本设备上的密钥已清除", "unreachable.per_1m":"每 1M", "unreachable.provider_prefix":"供应商：", "ui.auth.find_key":"在哪里找到我的密钥？", "ui.auth.run_li":"运行 <code>docker compose up</code>（或 <code>uvicorn app.main:app</code>）。", "ui.auth.first_run_li":"首次启动时，服务器会打印：<br><code class=\"code-block\">✓ orcarouter-lite ready. API key: sk-orca-...</code>", "ui.auth.copy_paste":"复制该字符串并粘贴到上方输入框。", "ui.auth.reset_p":"找不到了？删除 <code>orcarouter.db</code>（以及 <code>data/</code> 数据卷）后重启，即可重置工作区。", "ui.common.language":"语言", "ui.common.copy_base_tip":"复制你的 Base URL", "ui.common.logout_tip":"清除 API 密钥（本设备）", "ui.overview.spend_tip":"最近 7 天的所有上游成本之和", "ui.overview.spend_label":"花费（7 天）", "ui.overview.savings_tip":"上：同一流量的 GPT-4o 对比。下：hosted-auto 通过触达你没有密钥的更便宜模型可解锁的额外节省。", "ui.overview.routing_savings":"路由节省", "ui.overview.vs_hosted_auto":"对比 hosted-auto", "ui.overview.latency_tip":"最近请求的真实中位延迟（原始样本，非平均值）", "ui.overview.p50_label":"p50 延迟", "ui.overview.models_tip":"从已配置的供应商密钥与目录发现的模型", "ui.overview.models_label":"可用模型", "ui.overview.quick_start":"快速开始", "ui.overview.quick_sub":"已就绪 — 将任意 OpenAI SDK 指向你的 Base URL。", "ui.common.copy_snippet_tip":"复制示例代码", "ui.overview.auto_hint":"使用 <code>model=\"auto\"</code> 让路由器挑选最便宜且满足能力的模型。", "ui.overview.recent_title":"最近活动", "ui.overview.recent_sub":"最近经由此服务器路由的 5 次请求。", "ui.common.view_all":"查看全部", "ui.hosted.title":"Hosted 回退<span class=\"pill\" id=\"hosted-status-pill\">Not configured</span>", "ui.hosted.card_sub":"一个密钥，所有模型。任何你没有本地密钥的模型的标准回退方案。注册即送 <strong>$5</strong> 试用额度 — 无需信用卡。", "ui.hosted.get_key_on_site":"在 orcarouter.ai 获取你的密钥", "ui.hosted.step1_hint":"在新标签页打开 Token 控制台 — 在那里复制你的 <code>sk-orca-*</code> 密钥。", "ui.hosted.register":"还没有账号？注册即享 $5 免费额度", "ui.hosted.step2_hint":"回到这里，粘贴密钥并激活。", "ui.hosted.api_key_label":"Hosted API 密钥", "ui.hosted.paste_tip":"从剪贴板粘贴", "ui.common.paste":"粘贴", "ui.hosted.activate":"激活回退", "ui.hosted.unreachable_intro":"今天无法触达的模型 — hosted 可解锁全部：", "ui.hosted.disable_tip":"停用 Hosted 回退", "ui.hosted.remove_key":"移除密钥", "ui.hosted.onboarding_title":"新来的？两分钟完成全部设置", "ui.hosted.onb1":"<span class=\"check\"></span>至少添加一个<a href=\"#\" data-go-tab=\"providers\">供应商密钥</a>", "ui.hosted.onb2":"<span class=\"check\"></span>选择<a href=\"#\" data-go-tab=\"routing\">路由策略</a>", "ui.hosted.onb3":"<span class=\"check\"></span>发送你的第一个请求（它会出现在<a href=\"#\" data-go-tab=\"analytics\">分析</a>中）", "ui.hosted.title_prov":"Hosted 回退<span class=\"pill\" id=\"providers-hosted-pill\">Not configured</span>", "ui.hosted.prov_sub":"无需逐个供应商注册即可覆盖长尾。免费 <strong>$5</strong> 额度，之后按成本计费。", "ui.hosted.get_key":"获取密钥", "ui.providers.title":"供应商密钥 <span class=\"pill\">BYOK</span>", "ui.providers.sub":"使用 AES-256-GCM 静态加密存储。同一供应商的 env 变量优先于数据库记录。", "ui.providers.name":"供应商", "ui.providers.api_key":"API 密钥", "ui.common.save_key":"保存密钥", "ui.common.provider":"供应商", "ui.common.prefix":"前缀", "ui.common.status":"状态", "ui.providers.empty_title":"尚无供应商密钥", "ui.providers.empty_sub":"至少添加一个即可开始路由真实流量。在上方选择供应商，或点击快捷添加。", "ui.routing.title":"路由策略", "ui.routing.sub":"当发送 <code>model=\"auto\"</code> 时，路由器如何在候选模型之间做选择。", "ui.routing.balanced":"均衡", "ui.routing.balanced_desc":"50/50 加权混合 AA 质量与成本。适合大多数团队的稳妥默认。", "ui.routing.recommended":"推荐", "ui.routing.cheapest":"最便宜", "ui.routing.cheapest_desc":"满足请求能力要求的前提下，每 Token 成本最低。", "ui.routing.fastest":"最快", "ui.routing.fastest_desc":"最高吞吐 + 最低首 Token 延迟，来自 Artificial Analysis 基准。适合聊天类 UI。", "ui.routing.quality":"质量", "ui.routing.quality_desc":"偏好前沿模型。最适合困难推理任务。", "ui.routing.pick_hint":"点击卡片即可切换策略，自动保存。", "ui.routing.how_title":"<code>model=\"auto\"</code> 如何工作", "ui.routing.how_sub":"三个过滤器，按顺序应用。", "ui.routing.cap_filter":"能力过滤。", "ui.routing.cap_desc":"路由器检查你的请求 — 是否包含图片？工具定义？<code>response_format=json</code>？— 并剔除无法处理的模型。", "ui.routing.prov_filter":"供应商过滤。", "ui.routing.prov_desc":"只有已配置供应商（或 hosted 上游覆盖）的模型才能存活。", "ui.routing.strat_rank":"策略排序。", "ui.routing.strat_rank_desc":"剩余候选按你上方选择的策略评分，胜出者被调用。", "ui.routing.resolved_hint":"所选模型会通过 <code>x-orca-resolved-model</code> 响应头返回给你的客户端；生效的策略以 <code>x-orca-routing-strategy</code> 回显。", "ui.routing.map_summary":"各策略如何映射到 LiteLLM Router", "ui.routing.map_strategy":"策略", "ui.routing.map_litellm":"litellm <code>routing_strategy</code>", "ui.routing.map_picks":"<code>model=\"auto\"</code> 的选择", "ui.routing.we_rank":"<code>None</code>（我们自行排序）", "ui.routing.map_balanced_desc":"50/50 归一化 AA 质量与反相成本；严格双轴覆盖", "ui.routing.map_cheapest_desc":"满足能力的最便宜选择（0.3 输入 + 0.7 输出混合成本）", "ui.routing.map_fastest_desc":"50/50 归一化 AA TPS 与反相 TTFT；严格双轴覆盖", "ui.routing.map_quality_desc":"最高 AA 智能指数（或手动覆盖）；未评分模型排在已评分之后", "ui.routing.map_foot":"策略控制两件事：<code>model=\"auto\"</code> 解析到哪个模型，以及 LiteLLM Router 如何在服务同一模型的部署之间选择（例如本地 OpenAI 密钥 + hosted 上游）。", "ui.analytics.spend_title":"按模型花费", "ui.analytics.latency_title":"按供应商延迟", "ui.analytics.latency_sub":"p50 与 p99 — 数据来自本地请求日志。", "ui.analytics.requests":"请求数", "ui.analytics.recent_title":"最近请求", "ui.analytics.recent_sub":"最新在前。点击行可复制其 Trace ID。", "ui.analytics.when":"时间", "ui.common.model":"模型", "ui.analytics.tokens":"Token（入 / 出）", "ui.analytics.latency":"延迟", "ui.analytics.no_traffic":"暂无流量", "ui.analytics.no_traffic_sub":"开始发送请求后，它们会实时显示在这里。", "ui.keys.intro":"每个密钥都用于在此 Lite 工作区验证客户端。明文仅在创建时显示<strong>一次</strong>。", "ui.keys.name":"名称", "ui.keys.create":"创建密钥", "ui.keys.save_warn":"请保存此密钥 — 之后不再显示。", "ui.common.copy_tip":"复制", "ui.keys.last_used":"最后使用", "ui.quality.setup_title":"设置质量评分", "ui.quality.setup_p1":"当前 <code>quality</code> 策略会选择最贵的模型 — 在新旗舰（Claude Opus 4.7、GPT-5.x）定价低于旧款后，这个代理逻辑已经失效。设置 Artificial Analysis API 密钥，改为按真实基准分数路由。", "ui.quality.setup_li1":"在 <a href=\"https://artificialanalysis.ai\" target=\"_blank\" rel=\"noopener\">artificialanalysis.ai</a> 免费注册并生成 API 密钥（免费档：每天 1,000 次请求，对 1 小时缓存足够）。", "ui.quality.setup_li2":"把它加到 <code>.env</code> 中的 <code>ARTIFICIAL_ANALYSIS_API_KEY=...</code> 并重启。", "ui.quality.setup_li3":"刷新此页面 — 分数会自动出现。", "ui.quality.setup_foot":"没有密钥时，<code>quality</code> 会回退到旧的基于成本的行为。<code>cheapest</code> / <code>balanced</code> / <code>fastest</code> 不受影响。你仍可在下方表格中对单个模型设置<strong>手动覆盖</strong> — 这些不需要 AA 密钥，存在时优先。", "ui.quality.refresh":"从 AA 刷新", "ui.quality.preview_title":"此刻 <code>model=\"auto\"</code> 将解析为：", "ui.quality.models_title":"模型", "ui.quality.models_sub":"编辑一行的<strong>手动</strong>列可覆盖路由决策所用的 AA 分数。手动值优先于 AA。当你的内部评估与其不一致、或 AA 尚未给某模型评分时使用。", "ui.quality.manual":"手动", "ui.quality.effective":"生效", "ui.quality.tps_th_title":"每秒输出 Token（Artificial Analysis 中位数，各推理变体取最大）。— AA 尚未收录该模型时无数据。", "ui.quality.ttft_th_title":"首 Token 时间（秒，Artificial Analysis 中位数，各变体取最小 — 该模型的非推理快速模式）。— AA 尚未收录该模型时无数据。", "ui.quality.blended":"$/M 混合", "ui.quality.powered":"由 <a href=\"https://artificialanalysis.ai\" target=\"_blank\" rel=\"noopener\">Artificial Analysis</a> 提供支持 — 智能指数聚合了 MMLU-Pro、GPQA、MATH、HumanEval 等基准。按要求注明出处。", "ui.help.what_title":"什么是 OrcaRouter Lite？", "ui.help.what_body":"自托管的 OpenAI 兼容 LLM 路由器。自带供应商密钥（BYOK），将任意 OpenAI SDK 指向本地 Base URL，路由器会为每个请求挑选最便宜且满足能力的模型 — 可选回退到托管的 <a href=\"https://api.orcarouter.ai\" target=\"_blank\" rel=\"noreferrer\">api.orcarouter.ai</a>。", "ui.help.quick_title":"60 秒快速开始", "ui.help.qs1":"在<a href=\"#\" data-go-tab=\"providers\">供应商</a>页添加供应商密钥（或在 env 中设置 <code>OPENAI_API_KEY</code>）。", "ui.help.qs2":"可选：选择<a href=\"#\" data-go-tab=\"routing\">路由策略</a>。", "ui.help.qs3":"将此 URL 用作 OpenAI <code>base_url</code>：<code id=\"help-base-url\">http://localhost:8000/v1</code>", "ui.help.qs4":"使用登录时的 <code>sk-orca-*</code> 密钥作为 API 密钥。", "ui.help.kb_title":"键盘快捷键", "ui.help.kb_tabs":"切换标签页", "ui.help.kb_palette":"命令面板", "ui.help.kb_help":"开关此帮助", "ui.help.kb_close":"关闭抽屉 / 面板", "ui.help.further_title":"进一步了解", },
  hi: { "auth.tagline":"ओपन सोर्स। सिंगल टेनेंट।","auth.welcome":"वापसी पर स्वागत है","auth.subtitle":"पहले रन पर सर्वर लॉग में छपी sk-orca-* कुंजी पेस्ट करें। यह केवल इस ब्राउज़र के localStorage में रहेगी।","auth.api_key":"API कुंजी","auth.continue":"जारी रखें","nav.search":"खोज","nav.overview":"अवलोकन","nav.providers":"प्रदाता","nav.routing":"रूटिंग","nav.analytics":"एनालिटिक्स","nav.api_keys":"API कुंजियाँ","nav.help_docs":"सहायता और दस्तावेज़","nav.sign_out":"साइन आउट","status.connected":"कनेक्टेड","status.disconnected":"डिस्कनेक्टेड","auth.checking":"जाँच हो रही है…","auth.welcome_aboard":"स्वागत है।","auth.key_invalid":"यह कुंजी काम नहीं कर रही। sk-orca- प्रीफिक्स जाँचें…","tab.overview.title":"ओवरव्यू","tab.overview.sub":"आपका सिंगल-टेनेंट LLM राउटर एक नज़र में।","tab.providers.title":"प्रोवाइडर कुंजियाँ","tab.providers.sub":"BYOK — स्टोरेज में एन्क्रिप्टेड, अपस्ट्रीम LLM कॉल के लिए उपयोग।","tab.routing.title":"रूटिंग","tab.routing.sub":"model='auto' हर अनुरोध के लिए सही मॉडल कैसे चुनता है।","tab.analytics.title":"एनालिटिक्स","tab.analytics.sub":"केवल स्थानीय खर्च, लेटेंसी और अनुरोध इतिहास।","tab.keys.title":"API कुंजियाँ","tab.keys.sub":"इस Lite वर्कस्पेस पर क्लाइंट प्रमाणित करने वाले टोकन।" },
  es: { "auth.tagline":"Código abierto. Inquilino único.","auth.welcome":"Bienvenido de nuevo","auth.subtitle":"Pega la clave sk-orca-* mostrada en los logs del servidor en el primer inicio. Solo se guarda en este navegador mediante localStorage.","auth.api_key":"Clave API","auth.continue":"Continuar","nav.search":"Buscar","nav.overview":"Resumen","nav.providers":"Proveedores","nav.routing":"Enrutamiento","nav.analytics":"Analíticas","nav.api_keys":"Claves API","nav.help_docs":"Ayuda y documentación","nav.sign_out":"Cerrar sesión","status.connected":"Conectado","status.disconnected":"Desconectado","auth.checking":"Verificando…","auth.welcome_aboard":"Bienvenido.","auth.key_invalid":"Esa clave no funcionó. Verifica el prefijo sk-orca-…","tab.overview.title":"Resumen","tab.overview.sub":"Tu enrutador LLM de inquilino único de un vistazo.","tab.providers.title":"Claves de proveedor","tab.providers.sub":"BYOK — cifradas en reposo, usadas para llamar a LLMs upstream.","tab.routing.title":"Enrutamiento","tab.routing.sub":"Cómo model='auto' elige el modelo adecuado para cada solicitud.","tab.analytics.title":"Analíticas","tab.analytics.sub":"Gasto, latencia e historial de solicitudes solo local.","tab.keys.title":"Claves API","tab.keys.sub":"Tokens que autentican clientes en este espacio Lite." },
  pt: { "auth.tagline":"Código aberto. Locatário único.","auth.welcome":"Bem-vindo de volta","auth.subtitle":"Cole a chave sk-orca-* exibida nos logs do servidor na primeira execução. Armazenada apenas neste navegador via localStorage.","auth.api_key":"Chave API","auth.continue":"Continuar","nav.search":"Pesquisar","nav.overview":"Visão geral","nav.providers":"Provedores","nav.routing":"Roteação","nav.analytics":"Análises","nav.api_keys":"Chaves API","nav.help_docs":"Ajuda e docs","nav.sign_out":"Sair","status.connected":"Conectado","status.disconnected":"Desconectado","auth.checking":"Verificando…","auth.welcome_aboard":"Boas-vindas.","auth.key_invalid":"Essa chave não funcionou. Verifique o prefixo sk-orca-…","tab.overview.title":"Visão geral","tab.overview.sub":"Seu roteador LLM single-tenant em um relance.","tab.providers.title":"Chaves de provedor","tab.providers.sub":"BYOK — criptografadas em repouso, usadas para chamar LLMs upstream.","tab.routing.title":"Roteamento","tab.routing.sub":"Como model='auto' escolhe o modelo certo para cada solicitação.","tab.analytics.title":"Análises","tab.analytics.sub":"Gasto, latência e histórico de solicitações apenas locais.","tab.keys.title":"Chaves API","tab.keys.sub":"Tokens que autenticam clientes neste workspace Lite." },
  ru: { "auth.tagline":"Открытый исходный код. Один арендатор.","auth.welcome":"С возвращением","auth.subtitle":"Вставьте ключ sk-orca-*, показанный в логах сервера при первом запуске. Он хранится только в localStorage этого браузера.","auth.api_key":"API-ключ","auth.continue":"Продолжить","nav.search":"Поиск","nav.overview":"Обзор","nav.providers":"Провайдеры","nav.routing":"Маршрутизация ИИ","nav.analytics":"Аналитика","nav.api_keys":"API-ключи","nav.help_docs":"Помощь и документация","nav.sign_out":"Выйти","status.connected":"Подключено","status.disconnected":"Отключено","auth.checking":"Проверка…","auth.welcome_aboard":"Добро пожаловать.","auth.key_invalid":"Ключ не подошел. Проверьте префикс sk-orca-…","tab.overview.title":"Обзор","tab.overview.sub":"Ваш single-tenant маршрутизатор LLM в одном экране.","tab.providers.title":"Ключи провайдеров","tab.providers.sub":"BYOK — шифруются при хранении, используются для вызова внешних LLM.","tab.routing.title":"Маршрутизация","tab.routing.sub":"Как model='auto' выбирает подходящую модель для каждого запроса.","tab.analytics.title":"Аналитика","tab.analytics.sub":"Локальные расходы, задержка и история запросов.","tab.keys.title":"API-ключи","tab.keys.sub":"Токены для аутентификации клиентов в этом Lite workspace." },
  ja: { "auth.tagline":"オープンソース。シングルテナント。","auth.welcome":"おかえりなさい","auth.subtitle":"初回起動時にサーバーログへ表示された sk-orca-* キーを貼り付けてください。localStorage にのみ保存されます。","auth.api_key":"APIキー","auth.continue":"続行","nav.search":"検索","nav.overview":"概要","nav.providers":"プロバイダー","nav.routing":"経路制御","nav.analytics":"分析","nav.api_keys":"APIキー","nav.help_docs":"ヘルプとドキュメント","nav.sign_out":"サインアウト","status.connected":"接続済み","status.disconnected":"未接続","auth.checking":"確認中…","auth.welcome_aboard":"ようこそ。","auth.key_invalid":"キーが無効です。接頭辞 sk-orca- を確認してください…","tab.overview.title":"概要","tab.overview.sub":"シングルテナント LLM ルーターの概要。","tab.providers.title":"プロバイダーキー","tab.providers.sub":"BYOK — 保存時に暗号化され、上流 LLM 呼び出しに使用。","tab.routing.title":"ルーティング","tab.routing.sub":"model='auto' が各リクエストに最適なモデルを選択する方法。","tab.analytics.title":"分析","tab.analytics.sub":"ローカル限定のコスト・遅延・リクエスト履歴。","tab.keys.title":"APIキー","tab.keys.sub":"この Lite ワークスペースでクライアント認証に使うトークン。" },
  de: { "auth.tagline":"Open Source. Einzelmandant.","auth.welcome":"Willkommen zurück","auth.subtitle":"Fügen Sie den beim ersten Start in den Server-Logs ausgegebenen sk-orca-* Schlüssel ein. Er wird nur in diesem Browser per localStorage gespeichert.","auth.api_key":"API-Schlüssel","auth.continue":"Weiter","nav.search":"Suchen","nav.overview":"Übersicht","nav.providers":"Anbieter","nav.routing":"Weiterleitung","nav.analytics":"Analysen","nav.api_keys":"API-Schlüssel","nav.help_docs":"Hilfe & Doku","nav.sign_out":"Abmelden","status.connected":"Verbunden","status.disconnected":"Getrennt","auth.checking":"Prüfe…","auth.welcome_aboard":"Willkommen an Bord.","auth.key_invalid":"Dieser Schlüssel funktioniert nicht. Prüfen Sie das Präfix sk-orca-…","tab.overview.title":"Übersicht","tab.overview.sub":"Ihr Single-Tenant-LLM-Router auf einen Blick.","tab.providers.title":"Anbieterschlüssel","tab.providers.sub":"BYOK — im Ruhezustand verschlüsselt, für Upstream-LLM-Aufrufe genutzt.","tab.routing.title":"Routing","tab.routing.sub":"Wie model='auto' für jede Anfrage das richtige Modell auswählt.","tab.analytics.title":"Analysen","tab.analytics.sub":"Nur lokale Ausgaben, Latenz und Anfrageverlauf.","tab.keys.title":"API-Schlüssel","tab.keys.sub":"Token zur Authentifizierung von Clients in diesem Lite-Workspace." },
  fr: { "auth.tagline":"Open source. Locataire unique.","auth.welcome":"Bon retour","auth.subtitle":"Collez la clé sk-orca-* affichée dans les logs serveur au premier démarrage. Elle est stockée uniquement dans ce navigateur via localStorage.","auth.api_key":"Clé API","auth.continue":"Continuer","nav.search":"Rechercher","nav.overview":"Vue d'ensemble","nav.providers":"Fournisseurs","nav.routing":"Routage IA","nav.analytics":"Analytique","nav.api_keys":"Clés API","nav.help_docs":"Aide et docs","nav.sign_out":"Se déconnecter","status.connected":"Connecté","status.disconnected":"Déconnecté","auth.checking":"Vérification…","auth.welcome_aboard":"Bienvenue.","auth.key_invalid":"Cette clé n'a pas fonctionné. Vérifiez le préfixe sk-orca-…","tab.overview.title":"Vue d'ensemble","tab.overview.sub":"Votre routeur LLM mono-locataire en un coup d'œil.","tab.providers.title":"Clés fournisseur","tab.providers.sub":"BYOK — chiffrées au repos, utilisées pour appeler les LLM amont.","tab.routing.title":"Routage","tab.routing.sub":"Comment model='auto' choisit le bon modèle pour chaque requête.","tab.analytics.title":"Analytique","tab.analytics.sub":"Dépenses, latence et historique des requêtes en local uniquement.","tab.keys.title":"Clés API","tab.keys.sub":"Jetons qui authentifient les clients sur cet espace Lite." },
  it: { "auth.tagline":"Open source. Tenant singolo.","auth.welcome":"Bentornato","auth.subtitle":"Incolla la chiave sk-orca-* mostrata nei log del server al primo avvio. Viene salvata solo in questo browser tramite localStorage.","auth.api_key":"Chiave API","auth.continue":"Continua","nav.search":"Cerca","nav.overview":"Panoramica","nav.providers":"Provider","nav.routing":"Smistamento","nav.analytics":"Analitica","nav.api_keys":"Chiavi API","nav.help_docs":"Aiuto e documentazione","nav.sign_out":"Disconnetti","status.connected":"Connesso","status.disconnected":"Disconnesso","auth.checking":"Verifica…","auth.welcome_aboard":"Benvenuto.","auth.key_invalid":"La chiave non ha funzionato. Controlla il prefisso sk-orca-…","tab.overview.title":"Panoramica","tab.overview.sub":"Il tuo router LLM single-tenant a colpo d'occhio.","tab.providers.title":"Chiavi provider","tab.providers.sub":"BYOK — crittografate a riposo, usate per chiamare LLM upstream.","tab.routing.title":"Instradamento","tab.routing.sub":"Come model='auto' sceglie il modello giusto per ogni richiesta.","tab.analytics.title":"Analitica","tab.analytics.sub":"Spesa locale, latenza e cronologia richieste.","tab.keys.title":"Chiavi API","tab.keys.sub":"Token che autenticano i client in questo workspace Lite." },
  ar: { "auth.tagline":"مفتوح المصدر. مستأجر واحد.","auth.welcome":"مرحبًا بعودتك","auth.subtitle":"ألصق مفتاح sk-orca-* المطبوع في سجلات الخادم عند التشغيل الأول. يُخزَّن فقط في هذا المتصفح عبر localStorage.","auth.api_key":"مفتاح API","auth.continue":"متابعة","nav.search":"بحث","nav.overview":"نظرة عامة","nav.providers":"المزوّدون","nav.routing":"توجيه الطلبات","nav.analytics":"التحليلات","nav.api_keys":"مفاتيح API","nav.help_docs":"المساعدة والوثائق","nav.sign_out":"تسجيل الخروج","status.connected":"متصل","status.disconnected":"غير متصل","auth.checking":"جارٍ التحقق…","auth.welcome_aboard":"مرحبًا بك.","auth.key_invalid":"هذا المفتاح لم يعمل. تحقّق من البادئة sk-orca-…","tab.overview.title":"نظرة عامة","tab.overview.sub":"موجّه LLM أحادي المستأجر بنظرة سريعة.","tab.providers.title":"مفاتيح المزوّدين","tab.providers.sub":"BYOK — مشفّرة أثناء التخزين وتُستخدم لاستدعاء نماذج LLM الخارجية.","tab.routing.title":"التوجيه","tab.routing.sub":"كيف يختار model='auto' النموذج المناسب لكل طلب.","tab.analytics.title":"التحليلات","tab.analytics.sub":"الإنفاق والزمن والسجل المحلي للطلبات فقط.","tab.keys.title":"مفاتيح API","tab.keys.sub":"رموز مصادقة العملاء في مساحة Lite هذه." },
  ko: { "auth.tagline":"오픈 소스. 단일 테넌트.","auth.welcome":"다시 오신 것을 환영합니다","auth.subtitle":"첫 실행 시 서버 로그에 출력된 sk-orca-* 키를 붙여넣으세요. 이 브라우저의 localStorage에만 저장됩니다.","auth.api_key":"API 키","auth.continue":"계속","nav.search":"검색","nav.overview":"개요","nav.providers":"공급자","nav.routing":"경로 지정","nav.analytics":"분석","nav.api_keys":"API 키","nav.help_docs":"도움말 및 문서","nav.sign_out":"로그아웃","status.connected":"연결됨","status.disconnected":"연결 끊김","auth.checking":"확인 중…","auth.welcome_aboard":"환영합니다.","auth.key_invalid":"키가 올바르지 않습니다. sk-orca- 접두사를 확인하세요…","tab.overview.title":"개요","tab.overview.sub":"싱글 테넌트 LLM 라우터를 한눈에 확인하세요.","tab.providers.title":"공급자 키","tab.providers.sub":"BYOK — 저장 시 암호화되며 상위 LLM 호출에 사용됩니다.","tab.routing.title":"라우팅","tab.routing.sub":"model='auto'가 요청별로 적절한 모델을 고르는 방식입니다.","tab.analytics.title":"분석","tab.analytics.sub":"로컬 전용 비용, 지연 시간, 요청 기록.","tab.keys.title":"API 키","tab.keys.sub":"Lite 워크스페이스에서 클라이언트를 인증하는 토큰." },
};
// Provider ids must match catalog provider ids (packages/litellm_adapter/catalog.py
// `_PROVIDER_BY_LITELLM_KEY`) and Settings env-key fields (app/config.py
// `_PROVIDERS_FROM_ENV`). Labels follow the provider's own brand spelling so
// operators recognize them without ambiguity — "xAI" with the lowercase x is
// deliberate (Grok's parent company), distinct from "Groq" the inference
// hardware company.
const PROVIDERS_KNOWN = [
  { id: "openai",      label: "OpenAI"      },
  { id: "anthropic",   label: "Anthropic"   },
  { id: "google",      label: "Google"      },
  { id: "xai",         label: "xAI (Grok)"  },
  { id: "deepseek",    label: "DeepSeek"    },
  { id: "groq",        label: "Groq"        },
  { id: "together",    label: "Together"    },
  { id: "fireworks",   label: "Fireworks"   },
  { id: "orcarouter",  label: "OrcaRouter (hosted)" },
];
const TAB_META = {
  overview:  { title: "tab.overview.title",  sub: "tab.overview.sub" },
  providers: { title: "tab.providers.title", sub: "tab.providers.sub" },
  routing:   { title: "tab.routing.title",   sub: "tab.routing.sub" },
  analytics: { title: "tab.analytics.title", sub: "tab.analytics.sub" },
  keys:      { title: "tab.keys.title",      sub: "tab.keys.sub" },
  quality:   { title: "tab.quality.title",   sub: "tab.quality.sub" },
};

const state = {
  apiKey: localStorage.getItem(KEY_STORAGE) || "",
  tab: "overview",
  providers: [],
  routing: { strategy: "balanced", preferred_models: [] },
  recent: [],
  spend: { total_microcents: 0, by_model: [] },
  latency: { by_provider: [] },
  savings: { saved_microcents: 0, savings_percent: 0, hosted_auto: null },
  models: [],
  hosted: { configured: false, source: null, signup_url: "https://www.orcarouter.ai/register", token_url: "https://www.orcarouter.ai/console/token", provider_name: "orcarouter" },
  unreachable: { hosted_configured: false, unreachable: [] },
  // Quality scoring (Artificial Analysis Intelligence Index + manual overrides)
  quality: { aa_index: { configured: false, source: "missing-key", matched_count: 0 }, models: [], override_count: 0 },
  qualityPreview: null,
  windowDays: 7,
  lang: "python",
  locale: "en",
};
const t = (k, vars) => {
  const s = I18N[state.locale]?.[k] || I18N.en[k] || k;
  return vars
    ? s.replace(/\{(\w+)\}/g, (_, n) => (n in vars ? String(vars[n]) : `{${n}}`))
    : s;
};
function detectLocale() {
  const saved = localStorage.getItem(LOCALE_KEY);
  if (saved && SUPPORTED_LOCALES.includes(saved)) return saved;
  const browser = (navigator.languages?.[0] || navigator.language || "en").toLowerCase();
  const base = browser.split("-")[0];
  return SUPPORTED_LOCALES.includes(base) ? base : "en";
}
function applyI18n() {
  document.documentElement.lang = state.locale;
  document.documentElement.dir = state.locale === "ar" ? "rtl" : "ltr";
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  // data-i18n-html: keys whose values contain markup (inline <code>/<a>).
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  // data-i18n-title: translate a title attribute without touching the content.
  $$("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  if (TAB_META[state.tab]) {
    $("#page-title").textContent = t(TAB_META[state.tab].title);
    $("#page-sub").textContent = t(TAB_META[state.tab].sub);
  }
}
function bindLocalePicker() {
  const sel = $("#language-select");
  if (!sel) return;
  sel.innerHTML = SUPPORTED_LOCALES.map((lc) => `<option value="${lc}">${LOCALE_LABELS[lc]}</option>`).join("");
  sel.value = state.locale;
  sel.addEventListener("change", () => {
    state.locale = sel.value;
    localStorage.setItem(LOCALE_KEY, state.locale);
    applyI18n();
    rerenderAll();
  });
}

function rerenderAll() {
  // Re-run every state-driven renderer so dynamic t() strings follow the
  // newly selected locale. Safe pre-auth: renderers only touch state and
  // static DOM nodes (empty state -> empty panels).
  renderOverview();
  renderProviders();
  renderQuickAdd();
  renderRouting();
  renderHostedCard();
  renderUnreachable();
  renderAnalytics();
  renderKeys();
  renderQuality();
  renderQualityPreview();
}

/* ─────────────── tiny utils ─────────────── */
const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const fmtUsd = (mc) => {
  // Single-tenant dev workloads: a single chat completion can cost
  // ~$0.000006 (6 microcents). Default $0.00 rendering hides that
  // entirely until the operator has run hundreds of requests, which
  // makes the dashboard look broken on day 1. Lean precise on the
  // small end — a developer reading $0.000148 understands it; a
  // developer reading $0.00 thinks the meter is busted.
  const usd = (mc || 0) / 1_000_000;
  if (usd === 0) return "$0";
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01)  return `$${usd.toFixed(5)}`;
  if (usd < 1)     return `$${usd.toFixed(3)}`;
  if (usd < 100)   return `$${usd.toFixed(2)}`;
  return `$${Math.round(usd).toLocaleString()}`;
};
const fmtNum = (n) => (n || 0).toLocaleString();
const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60)   return t("time.seconds_ago", { sec });
  if (sec < 3600) return t("time.minutes_ago", { min: Math.floor(sec / 60) });
  if (sec < 86400) return t("time.hours_ago", { hrs: Math.floor(sec / 3600) });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const escapeHtml = (s = "") =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));

// `https://api.example.com/v1` -> `api.example.com/v1`. The scheme is noise in
// a table cell (everything is https) and the full URL is in the title tooltip.
const shortBaseUrl = (s = "") => String(s).replace(/^https?:\/\//, "");

// Mirror of app/routes/analytics.py:_percentile — same nearest-rank
// algorithm, including Python's banker's rounding (round-half-to-even)
// for .5 ties so client-derived percentiles match the backend
// bit-for-bit on the same sample.
function bankersRound(x) {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff < 0.5) return floor;
  if (diff > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}
function percentile(values, pct) {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(s.length - 1, bankersRound((s.length - 1) * pct)));
  return Math.round(s[idx]);
}

/* ─────────────── HTTP ─────────────── */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.apiKey) headers["Authorization"] = `Bearer ${state.apiKey}`;
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 204) return null;
  let body = null;
  try { body = await r.json(); } catch { /* ignore */ }
  if (!r.ok) {
    const msg = body?.error?.message || body?.detail || r.statusText || t("common.request_failed");
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return body;
}

/* ─────────────── toasts ─────────────── */
const TOAST_ICONS = {
  ok:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  err:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  info: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
};
function toast(msg, kind = "ok", ms = 2400) {
  const region = $("#toast-region");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="ico">${TOAST_ICONS[kind] || TOAST_ICONS.info}</span><span>${escapeHtml(msg)}</span>`;
  region.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 220);
  }, ms);
}

/* ─────────────── clipboard ─────────────── */
async function copyToClipboard(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    if (btn) {
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    }
    toast(t("common.copy_ok"), "info", 1400);
    return true;
  } catch {
    toast(t("common.copy_blocked"), "err");
    return false;
  }
}

/* ==========================================================================
   AUTH
   ========================================================================== */
async function checkAuth() {
  if (!state.apiKey) return false;
  try {
    await api("/v1/keys");
    return true;
  } catch {
    return false;
  }
}

function showShell() {
  $("#auth-gate").hidden = true;
  $("#app-shell").hidden = false;
  pollHealth();
  // fire-and-forget — render once data arrives
  Promise.allSettled([
    loadProviders(),
    loadRouting(),
    loadAnalytics(),
    loadKeys(),
    loadModels(),
    loadHosted(),
    loadUnreachable(),
  ]).then(() => {
    renderProviders();
    renderRouting();
    renderAnalytics();
    renderKeys();
    renderOverview();
    renderQuickstart();
    renderHostedCard();
    renderUnreachable();
    syncOnboarding();
  });
}

function showGate() {
  $("#app-shell").hidden = true;
  $("#auth-gate").hidden = false;
  $("#api-key-input").focus();
}

/* ==========================================================================
   TABS / ROUTING
   ========================================================================== */
function setTab(tab) {
  if (!TAB_META[tab]) return;
  state.tab = tab;
  history.replaceState(null, "", `#${tab}`);
  $$("#tabs .nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $$(".panel").forEach((p) => p.classList.remove("active"));
  $(`#panel-${tab}`).classList.add("active");
  $("#page-title").textContent = t(TAB_META[tab].title);
  $("#page-sub").textContent = t(TAB_META[tab].sub);
  // refresh the tab's data so it's fresh-on-view
  if (tab === "analytics") loadAnalytics().then(renderAnalytics);
  if (tab === "providers") {
    Promise.all([loadProviders(), loadHosted(), loadUnreachable()]).then(() => {
      renderProviders();
      renderHostedCard();
      renderUnreachable();
    });
  }
  if (tab === "keys")      loadKeys().then(renderKeys);
  if (tab === "overview")  {
    Promise.all([loadHosted(), loadUnreachable()]).then(() => {
      renderOverview();
      renderHostedCard();
      renderUnreachable();
    });
  }
  if (tab === "quality") {
    Promise.all([loadQuality(), loadQualityPreview()]).then(() => {
      renderQuality();
      renderQualityPreview();
    });
  }
}

function bindTabs() {
  $$("#tabs .nav-item").forEach((b) =>
    b.addEventListener("click", () => setTab(b.dataset.tab))
  );
  // Inline anchor "go to tab" links
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-go-tab]");
    if (t) {
      e.preventDefault();
      setTab(t.dataset.goTab);
    }
  });
  // Initial tab from hash
  const initial = (location.hash || "").replace("#", "");
  if (TAB_META[initial]) setTab(initial);
}

/* ==========================================================================
   PROVIDERS
   ========================================================================== */
async function loadProviders() {
  try {
    const data = await api("/v1/providers");
    state.providers = data.providers || [];
  } catch (e) {
    toast(t("providers.load_err", { msg: e.message }), "err");
  }
}

function renderProviders() {
  const tbody = $("#providers-table tbody");
  const empty = $("#providers-empty");
  tbody.innerHTML = "";
  if (!state.providers.length) {
    empty.classList.add("shown");
  } else {
    empty.classList.remove("shown");
    state.providers.forEach((p) => {
      const tr = document.createElement("tr");
      tr.className = "row-in";
      // Env-sourced keys come from .env / process env, not the DB.
      // Disabling delete avoids a confusing "no-op" — the row would
      // come right back on next load because the env var is still set.
      // Operator can still PUT a DB-sourced key for the same provider
      // to override the env value (the runtime resolver picks DB > env).
      const isEnv = p.source === "env";
      const sourceBadge = isEnv
        ? `<span class="pill muted" title="${t("providers.env_title")}">env</span>`
        : '';
      // A base URL means this provider is a custom endpoint; its model list is
      // discovered from that endpoint rather than the built-in catalog.
      const endpointCell = p.api_base
        ? `<code title="${escapeHtml(p.api_base)}">${escapeHtml(shortBaseUrl(p.api_base))}</code>`
        : `<span class="muted small" title="${t("providers.endpoint_default_title")}">${escapeHtml(t("providers.endpoint_default"))}</span>`;
      const rescanBtn = (!isEnv && p.api_base)
        ? `<button class="btn btn-ghost btn-sm rescan-prov" data-prov="${escapeHtml(p.provider)}" title="${t("providers.rescan_title")}">${escapeHtml(t("providers.rescan"))}</button> `
        : '';
      const removeBtn = isEnv
        ? `<span class="muted small" title="${t("providers.env_managed_title")}">env-managed</span>`
        : `<button class="btn btn-ghost btn-sm btn-danger del-prov" data-prov="${escapeHtml(p.provider)}">${escapeHtml(t("common.remove"))}</button>`;
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.provider)}</strong> ${sourceBadge}</td>
        <td>${endpointCell}</td>
        <td><code>${escapeHtml(p.key_prefix || "—")}</code></td>
        <td>${p.is_enabled
          ? `<span class="pill ok">${escapeHtml(t("common.enabled"))}</span>`
          : `<span class="pill muted">${escapeHtml(t("common.disabled"))}</span>`}</td>
        <td class="th-actions">${rescanBtn}${removeBtn}</td>
      `;
      tbody.appendChild(tr);
    });
    $$(".rescan-prov").forEach((b) =>
      b.addEventListener("click", async () => {
        const prov = b.dataset.prov;
        b.disabled = true;
        try {
          const res = await api(`/v1/providers/${encodeURIComponent(prov)}/refresh-models`, {
            method: "POST",
          });
          toast(t(res.count === 1 ? "providers.found_model" : "providers.found_models", { count: res.count, prov }), "ok");
          await Promise.all([loadProviders(), loadUnreachable()]);
          renderProviders();
          renderUnreachable();
          renderOverview();
        } catch (e) {
          toast(e.message, "err");
        } finally {
          b.disabled = false;
        }
      })
    );
    $$(".del-prov").forEach((b) =>
      b.addEventListener("click", async () => {
        const prov = b.dataset.prov;
        if (!confirm(t("providers.remove_confirm", { prov }))) return;
        try {
          await api(`/v1/providers/${prov}`, { method: "DELETE" });
          toast(t("providers.removed", { prov }), "ok");
          await Promise.all([loadProviders(), loadHosted(), loadUnreachable()]);
          renderProviders();
          renderQuickAdd();
          renderHostedCard();
          renderUnreachable();
          renderOverview();
          syncOnboarding();
        } catch (e) {
          toast(e.message, "err");
        }
      })
    );
  }
  renderQuickAdd();
}

function renderQuickAdd() {
  const wrap = $("#provider-quickadd");
  if (!wrap) return;
  // DB-sourced providers are "fully configured" — disable the chip so
  // the operator doesn't accidentally re-PUT and clobber a known-good key.
  // ENV-sourced providers stay clickable: clicking pre-fills the form so
  // the operator can write a DB row that overrides the env value (matches
  // the runtime resolver's DB > env precedence).
  const dbConfigured = new Set(
    state.providers.filter((p) => p.source === "db").map((p) => p.provider)
  );
  const envConfigured = new Set(
    state.providers.filter((p) => p.source === "env").map((p) => p.provider)
  );
  wrap.innerHTML = `<span class="muted" style="font-size:12px;align-self:center;margin-right:4px">${t("providers.quick_add")}</span>` +
    PROVIDERS_KNOWN.map((p) => {
      const isDb = dbConfigured.has(p.id);
      const isEnv = envConfigured.has(p.id);
      const cls = isDb ? "configured" : (isEnv ? "env-override" : "");
      const disabled = isDb ? "disabled" : "";
      const title = isEnv
        ? t("providers.chip_env_title", { label: p.label })
        : "";
      return `<button class="chip ${cls}" data-prov-pick="${p.id}" ${disabled} ${title ? `title="${escapeHtml(title)}"` : ""}>
        ${escapeHtml(p.label)}${isEnv ? ` <span class="small muted">${t("providers.env_override")}</span>` : ""}
      </button>`;
    }).join("");
  $$("[data-prov-pick]").forEach((b) =>
    b.addEventListener("click", () => {
      const sel = $("#provider-name");
      sel.value = b.dataset.provPick;
      $("#provider-key").focus();
    })
  );
}

function renderProviderOptions() {
  const dl = $("#provider-options");
  if (!dl) return;
  // Single source of truth: PROVIDERS_KNOWN, which must stay in sync with the
  // backend's env-key fields (app/config.py `_PROVIDERS_FROM_ENV`). Rendering
  // the datalist from it means the free-text suggestions can't drift away from
  // the quick-add chips below them.
  dl.innerHTML = PROVIDERS_KNOWN.map(
    (p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`
  ).join("");
}

function bindProviderForm() {
  $("#provider-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const provider = $("#provider-name").value.trim().toLowerCase();
    const apiKeyVal = $("#provider-key").value.trim();
    const baseVal = ($("#provider-base")?.value || "").trim();
    if (!provider) {
      toast(t("providers.name_required"), "err");
      return;
    }
    if (!apiKeyVal) {
      toast(t("providers.key_empty"), "err");
      return;
    }
    try {
      await api(`/v1/providers/${encodeURIComponent(provider)}`, {
        method: "PUT",
        body: JSON.stringify({ api_key: apiKeyVal, api_base: baseVal }),
      });
      $("#provider-key").value = "";
      $("#provider-base").value = "";
      toast(t("providers.saved", { provider }), "ok");
      await Promise.all([loadProviders(), loadHosted(), loadUnreachable()]);
      renderProviders();
      renderHostedCard();
      renderUnreachable();
      renderOverview();
      syncOnboarding();
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

/* ==========================================================================
   ROUTING
   ========================================================================== */
async function loadRouting() {
  try {
    const r = await api("/v1/routing");
    state.routing = r;
  } catch (e) {
    toast(t("routing.load_err", { msg: e.message }), "err");
  }
}

function renderRouting() {
  $$(".strategy-card").forEach((c) => {
    const selected = c.dataset.value === state.routing.strategy;
    c.classList.toggle("selected", selected);
    const input = c.querySelector("input");
    if (input) input.checked = selected;
  });
}

function bindRouting() {
  $$(".strategy-card").forEach((c) => {
    c.addEventListener("click", async (e) => {
      e.preventDefault();
      const val = c.dataset.value;
      if (val === state.routing.strategy) return;
      const prev = state.routing.strategy;
      state.routing.strategy = val;
      renderRouting();
      try {
        await api("/v1/routing", { method: "PUT", body: JSON.stringify({ strategy: val }) });
        toast(t("routing.strategy_saved", { val }), "ok");
        // Refresh the Quality preview so the operator sees the new
        // strategy's primary pick immediately. The preview reads workspace
        // strategy server-side (NOT a query param — avoids a race where the
        // dashboard's local default `balanced` overrides the just-saved
        // value before loadRouting() finishes on initial load).
        try {
          await loadQualityPreview();
          renderQualityPreview();
        } catch (_) { /* preview is non-critical, never block strategy change */ }
        syncOnboarding();
      } catch (err) {
        state.routing.strategy = prev;
        renderRouting();
        toast(err.message, "err");
      }
    });
  });
}

/* ==========================================================================
   ANALYTICS
   ========================================================================== */
async function loadAnalytics() {
  const days = state.windowDays;
  try {
    const [recent, spend, latency, savings] = await Promise.all([
      api(`/v1/analytics/recent?limit=50`),
      api(`/v1/analytics/spend?days=${days}`),
      api(`/v1/analytics/latency?days=${days}`),
      api(`/v1/analytics/savings?days=${days}&baseline=gpt-4o`).catch(() => null),
    ]);
    state.recent = recent.items || [];
    state.spend = spend;
    state.latency = latency;
    if (savings) state.savings = savings;
  } catch (e) {
    toast(t("analytics.load_err", { msg: e.message }), "err");
  }
}

/* ==========================================================================
   HOSTED FALLBACK + UNREACHABLE MODELS
   ========================================================================== */
async function loadHosted() {
  try {
    state.hosted = await api(`/v1/hosted`);
  } catch {
    // Non-fatal — card just stays in unconfigured state.
  }
}

async function loadUnreachable() {
  try {
    state.unreachable = await api(`/v1/analytics/unreachable?limit=8`);
  } catch {
    state.unreachable = { hosted_configured: false, unreachable: [] };
  }
}

function fmtPerMtok(perToken) {
  // litellm prices are USD per token; show as $/1M tokens.
  const perMillion = (perToken || 0) * 1_000_000;
  if (perMillion === 0) return "—";
  if (perMillion < 1) return `$${perMillion.toFixed(2)}`;
  return `$${perMillion.toFixed(2)}`;
}

function renderHostedCard() {
  const card = $("#hosted-card");
  if (!card) return;
  card.hidden = false;

  const pill = $("#hosted-status-pill");
  const cta = $("#hosted-cta");
  const active = $("#hosted-active");
  const signupBtn = $("#hosted-signup-btn");
  const providersPill = $("#providers-hosted-pill");
  const providersSignup = $("#providers-hosted-signup");
  const providersCard = $("#providers-hosted-card");

  // Primary CTA goes to the token console — that's the page with the
  // copyable sk-orca-* key. The secondary link is for users who don't
  // have an account yet.
  const tokenUrl = state.hosted.token_url || "https://www.orcarouter.ai/console/token";
  const signupUrl = state.hosted.signup_url || "https://www.orcarouter.ai/register";
  if (signupBtn) signupBtn.href = tokenUrl;
  if (providersSignup) providersSignup.href = tokenUrl;
  const registerLink = $("#hosted-register-link");
  if (registerLink) registerLink.href = signupUrl;

  // First run == no hosted key yet: the two-step "get your key" flow is
  // the most useful thing on the page, so it goes above the (empty) KPI
  // grid. Once configured it drops back to its normal slot.
  const panel = document.getElementById("panel-overview");
  if (panel && card.parentElement === panel) {
    if (!state.hosted.configured && panel.firstElementChild !== card) {
      panel.prepend(card);
    } else if (state.hosted.configured && panel.firstElementChild === card) {
      const help = document.getElementById("getting-started");
      if (help) panel.insertBefore(card, help);
      else panel.appendChild(card);
    }
  }

  if (state.hosted.configured) {
    pill.textContent = t("common.active");
    pill.className = "pill ok";
    cta.hidden = true;
    active.hidden = false;
    if (providersPill) { providersPill.textContent = t("common.active"); providersPill.className = "pill ok"; }
    if (providersCard) providersCard.hidden = true;

    // Hosted-active state: source line + extra savings projection.
    // Three branches: no comparable history yet, additional savings
    // detected, or already optimal (history exists but routing matches
    // the cheapest hosted-auto pick on every comparable request).
    const isEnv = state.hosted.source === "env";
    const ha = state.savings.hosted_auto;
    let haText;
    if (!ha || ha.comparable_request_count === 0) {
      haText = t("hosted.no_history");
    } else if (ha.saved_microcents > 0) {
      // savings_percent is computed against comparable spend only (rows
      // resolved to a catalog model), not total spend — keep the copy
      // honest so non-catalog traffic doesn't make the figure misleading.
      haText = t("hosted.savings_detected", { amount: fmtUsd(ha.saved_microcents), pct: ha.savings_percent });
    } else {
      haText = t("hosted.already_optimal");
    }
    $("#hosted-active-meta").innerHTML = isEnv
      ? t("hosted.env_active")
      : t("hosted.db_active");
    $("#hosted-savings").innerHTML = haText;
    // The Remove button DELETEs the DB row; with no DB row (env-only) it
    // would 404. Hide it and let the meta line explain how to disable.
    const removeBtn = $("#hosted-remove-btn");
    if (removeBtn) removeBtn.hidden = isEnv;
  } else {
    pill.textContent = t("common.not_configured");
    pill.className = "pill muted";
    cta.hidden = false;
    active.hidden = true;
    if (providersPill) { providersPill.textContent = t("common.not_configured"); providersPill.className = "pill muted"; }
    if (providersCard) providersCard.hidden = false;
  }
}

function renderUnreachable() {
  const wrap = $("#unreachable-list");
  const grid = $("#unreachable-grid");
  if (!wrap || !grid) return;
  const list = state.unreachable.unreachable || [];
  if (state.hosted.configured || list.length === 0) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  grid.innerHTML = list.map((m) => {
    const caps = [];
    if (m.supports_tools) caps.push("tools");
    if (m.supports_vision) caps.push("vision");
    if (m.supports_json_mode) caps.push("json");
    const capPills = caps.map((c) => `<span class="cap-pill">${c}</span>`).join("");
    return `
      <div class="unreachable-item" data-tooltip="${t("unreachable.provider_prefix")} ${escapeHtml(m.provider)} · ${fmtPerMtok(m.input_cost_per_token)}/$1M in · ${fmtPerMtok(m.output_cost_per_token)}/$1M out">
        <div class="unreachable-id"><code>${escapeHtml(m.id)}</code></div>
        <div class="unreachable-meta">
          <span class="unreachable-provider">${escapeHtml(m.provider)}</span>
          <span class="unreachable-price">${fmtPerMtok(m.input_cost_per_token)} / ${fmtPerMtok(m.output_cost_per_token)} ${t("unreachable.per_1m")}</span>
        </div>
        <div class="unreachable-caps">${capPills}</div>
      </div>`;
  }).join("");
}

function bindHostedForm() {
  // Step 1 is a link the user clicks, not a redirect we perform: the
  // token console opens in a new tab and the dashboard stays put, so
  // coming back to paste is one tab-switch away.
  const getKeyBtn = $("#hosted-signup-btn");
  if (getKeyBtn) {
    getKeyBtn.addEventListener("click", () => {
      const step1 = $("#hosted-step-1");
      if (step1) step1.classList.add("done");
      // They left for the key; when the tab regains focus, put the
      // cursor where the key goes. Once only, and never if they already
      // typed something.
      window.addEventListener("focus", function focusPaste() {
        window.removeEventListener("focus", focusPaste);
        const input = $("#hosted-key-input");
        if (input && !input.value && !state.hosted.configured) input.focus();
      });
    });
  }

  const pasteBtn = $("#hosted-paste-btn");
  if (pasteBtn) {
    pasteBtn.addEventListener("click", async () => {
      const input = $("#hosted-key-input");
      if (!input) return;
      try {
        const text = (await navigator.clipboard.readText()).trim();
        if (!text) { toast(t("hosted.clipboard_empty"), "err"); return; }
        input.value = text;
        input.focus();
      } catch {
        // Firefox has no readText for pages, and any browser can deny
        // the permission prompt. Ctrl+V still works — say so.
        input.focus();
        toast(t("hosted.paste_blocked"), "err");
      }
    });
  }

  const form = $("#hosted-key-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = $("#hosted-key-input").value.trim();
      if (!v) { toast(t("hosted.paste_hint"), "err"); return; }
      try {
        await api(`/v1/providers/orcarouter`, {
          method: "PUT",
          body: JSON.stringify({ api_key: v }),
        });
        $("#hosted-key-input").value = "";
        toast(t("hosted.activate_ok"), "ok");
        await Promise.all([loadHosted(), loadUnreachable(), loadProviders()]);
        renderHostedCard();
        renderUnreachable();
        renderProviders();
        renderOverview();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }
  const remove = $("#hosted-remove-btn");
  if (remove) {
    remove.addEventListener("click", async () => {
      if (!confirm(t("hosted.disable_confirm"))) return;
      try {
        await api(`/v1/providers/orcarouter`, { method: "DELETE" });
        toast(t("hosted.disabled"), "info");
        await Promise.all([loadHosted(), loadUnreachable(), loadProviders()]);
        renderHostedCard();
        renderUnreachable();
        renderProviders();
        renderOverview();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }
}

function renderAnalytics() {
  // Spend summary
  const totalReq = state.spend.by_model.reduce((a, m) => a + m.request_count, 0);
  $("#spend-summary").innerHTML = t("analytics.spend_summary", {
    days: state.spend.days || state.windowDays,
    cost: fmtUsd(state.spend.total_microcents),
    n: fmtNum(totalReq),
  });

  // Bar chart
  const chart = $("#bar-chart");
  if (!state.spend.by_model.length) {
    chart.innerHTML = `<div class="empty-mini">
      <p>${t("analytics.no_spend")}</p>
      <p class="muted">${t("analytics.no_spend_hint")}</p>
    </div>`;
  } else {
    const max = Math.max(...state.spend.by_model.map((m) => m.cost_microcents)) || 1;
    chart.innerHTML = state.spend.by_model.slice(0, 10).map((m) => {
      const pct = Math.max(2, (m.cost_microcents / max) * 100);
      return `
        <div class="bar-row" data-tooltip="${t("analytics.chart_tooltip", { n: fmtNum(m.request_count), cost: fmtUsd(m.cost_microcents) })}">
          <div class="bar-label">${escapeHtml(m.model || "—")}</div>
          <div class="bar-track"><div class="bar-fill" style="right:${100 - pct}%"></div></div>
          <div class="bar-value">${fmtUsd(m.cost_microcents)} <span class="reqs">${fmtNum(m.request_count)} ${t("analytics.req")}</span></div>
        </div>`;
    }).join("");
  }

  // Latency table
  const lt = $("#latency-table tbody");
  if (!state.latency.by_provider.length) {
    lt.innerHTML = `<tr><td colspan="4" class="muted" style="text-align:center;padding:24px">${t("analytics.no_data_window")}</td></tr>`;
  } else {
    lt.innerHTML = state.latency.by_provider.map((p) => `
      <tr class="row-in">
        <td><strong>${escapeHtml(p.provider)}</strong></td>
        <td>${fmtNum(p.request_count)}</td>
        <td>${fmtNum(p.p50_ms)} ms</td>
        <td>${fmtNum(p.p99_ms)} ms</td>
      </tr>
    `).join("");
  }

  // Recent table
  const rt = $("#recent-table tbody");
  const rEmpty = $("#recent-empty");
  if (!state.recent.length) {
    rt.innerHTML = "";
    rEmpty.hidden = false;
    rEmpty.classList.add("shown");
  } else {
    rEmpty.hidden = true;
    rEmpty.classList.remove("shown");
    rt.innerHTML = state.recent.map((it) => {
      const ok = (it.status_code || 0) < 400;
      const pillCls = ok ? "ok" : "err";
      const pillTxt = ok ? `${it.status_code} OK` : `${it.status_code} ${it.error_type || "error"}`;
      return `
        <tr class="row-in copy-row" data-trace="${escapeHtml(it.trace_id || "")}" data-tooltip="${t("analytics.trace_tip")}">
          <td>${fmtTime(it.created_at)}</td>
          <td><code>${escapeHtml(it.model_resolved || it.model_requested || "—")}</code></td>
          <td>${escapeHtml(it.provider || "—")}</td>
          <td>${fmtNum(it.input_tokens)} / ${fmtNum(it.output_tokens)}</td>
          <td>${fmtNum(it.latency_ms)} ms</td>
          <td><span class="pill ${pillCls}">${escapeHtml(pillTxt)}</span></td>
        </tr>`;
    }).join("");
    $$(".copy-row").forEach((row) =>
      row.addEventListener("click", () => {
        const tid = row.dataset.trace;
        if (tid) copyToClipboard(tid);
      })
    );
  }
}

function bindWindowSeg() {
  $$("#window-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", async () => {
      $$("#window-seg .seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.windowDays = parseInt(b.dataset.days, 10);
      await loadAnalytics();
      renderAnalytics();
      renderOverview();
    })
  );
}

/* ==========================================================================
   KEYS
   ========================================================================== */
async function loadKeys() {
  try {
    const data = await api("/v1/keys");
    state.keys = data.keys || [];
  } catch (e) {
    toast(t("keys.load_err", { msg: e.message }), "err");
  }
}

function renderKeys() {
  const tbody = $("#keys-table tbody");
  tbody.innerHTML = "";
  if (!state.keys || !state.keys.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">
      ${t("keys.empty")}
    </td></tr>`;
    return;
  }
  state.keys.forEach((k) => {
    const tr = document.createElement("tr");
    tr.className = "row-in";
    tr.innerHTML = `
      <td><strong>${escapeHtml(k.name)}</strong></td>
      <td><code>${escapeHtml(k.key_prefix)}</code></td>
      <td>${k.is_active ? `<span class="pill ok">${t("common.active")}</span>` : `<span class="pill muted">${t("common.revoked")}</span>`}</td>
      <td>${k.last_used_at ? fmtTime(k.last_used_at) : `<span class="muted">${t("common.never")}</span>`}</td>
      <td class="th-actions">
        ${k.is_active
          ? `<button class="btn btn-ghost btn-sm btn-danger rev-key" data-id="${escapeHtml(k.id)}" data-name="${escapeHtml(k.name)}">${escapeHtml(t("common.revoke"))}</button>`
          : ""}
      </td>
    `;
    tbody.appendChild(tr);
  });
  $$(".rev-key").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm(t("keys.revoke_confirm", { name: b.dataset.name }))) return;
      try {
        await api(`/v1/keys/${b.dataset.id}`, { method: "DELETE" });
        toast(t("keys.revoked", { name: b.dataset.name }), "ok");
        await loadKeys();
        renderKeys();
      } catch (e) {
        toast(e.message, "err");
      }
    })
  );
}

function bindKeyForm() {
  $("#key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("#key-name").value.trim();
    if (!name) { toast(t("keys.name_required"), "err"); return; }
    try {
      const r = await api("/v1/keys", { method: "POST", body: JSON.stringify({ name }) });
      $("#key-name").value = "";
      const display = $("#new-key-display");
      $("#new-key-value").textContent = r.api_key;
      display.hidden = false;
      $("#new-key-copy").onclick = (ev) => copyToClipboard(r.api_key, ev.currentTarget);
      toast(t("keys.created", { name }), "ok");
      await loadKeys();
      renderKeys();
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

/* ==========================================================================
   QUALITY (AA Intelligence Index + manual overrides)
   ========================================================================== */
async function loadQuality() {
  try {
    const data = await api("/v1/quality");
    state.quality = data;
  } catch (e) {
    toast(t("quality.load_err", { msg: e.message }), "err");
  }
}

async function loadQualityPreview() {
  try {
    state.qualityPreview = await api("/v1/quality/auto-preview");
  } catch (e) {
    state.qualityPreview = null;
  }
}

function renderQuality() {
  const aa = state.quality?.aa_index || {};
  const setupCard = $("#quality-setup-card");
  const statusCard = $("#quality-status-card");
  const tableCard = $("#quality-table-card");

  // Setup card is informational when no AA key — manual overrides still
  // work standalone, so the table card is always shown. Status card
  // (which surfaces AA freshness) is only meaningful when AA is wired up.
  const isConfigured = aa.source !== "missing-key";
  setupCard.hidden = isConfigured;
  statusCard.hidden = !isConfigured;
  tableCard.hidden = false;

  // Status line — only when AA is configured (the card itself is hidden
  // otherwise, but populating defensively avoids a blank flash on toggle).
  if (isConfigured) {
    const sourceLabel = {
      "live":         `<span class="pill ok">${t("quality.source_live")}</span>`,
      "stale-cache":  `<span class="pill warn">${t("quality.source_stale_aa")}</span>`,
      "stale-db":     `<span class="pill warn">${t("quality.source_stale_db")}</span>`,
      "error":        `<span class="pill err">${t("quality.source_error")}</span>`,
      "missing-key":  `<span class="pill muted">${t("quality.source_no_key")}</span>`,
    }[aa.source] || `<span class="pill">${escapeHtml(aa.source || t("quality.source_unknown"))}</span>`;

    $("#quality-status-line").innerHTML =
      `${sourceLabel} · ${t("quality.status_fmt", {
        matched: aa.matched_count || 0,
        total: aa.raw_count || 0,
        overrides: state.quality.override_count || 0,
        s: state.quality.override_count === 1 ? "" : "s",
      })}`;
  }

  renderQualityTable();
}

function renderQualityTable() {
  const tbody = $("#quality-table tbody");
  tbody.innerHTML = "";
  const rows = state.quality?.models || [];
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted" style="text-align:center;padding:24px">
      ${t("quality.empty")}
    </td></tr>`;
    return;
  }

  // Show top 60 by effective score; full table is 500+ entries which is
  // overwhelming. Add a search/filter later if needed.
  rows.slice(0, 60).forEach((m) => {
    const tr = document.createElement("tr");
    tr.className = "row-in";
    const aaCell = m.aa_score == null
      ? '<span class="muted">—</span>'
      : `<span title="${t("quality.aa_title")}">${m.aa_score.toFixed(0)}</span>`;
    const manualCell = m.manual_score == null
      ? `<button class="btn btn-ghost btn-sm set-override" data-id="${escapeHtml(m.id)}" data-aa="${m.aa_score ?? ""}">${escapeHtml(t("common.set"))}</button>`
      : `<strong>${m.manual_score.toFixed(0)}</strong>`;
    const effectiveCell = m.effective_score == null
      ? `<span class="muted">${t("quality.unscored")}</span>`
      : `<strong>${m.effective_score.toFixed(0)}</strong>`;
    // TPS / TTFT come from AA latency benchmarks — null when AA hasn't
    // indexed this model on that axis. Used by the `fastest` strategy.
    const tpsCell = m.tps == null
      ? '<span class="muted">—</span>'
      : `<span title="${t("quality.tps_title")}">${m.tps.toFixed(0)}</span>`;
    const ttftCell = m.ttft == null
      ? '<span class="muted">—</span>'
      : `<span title="${t("quality.ttft_title")}">${m.ttft.toFixed(2)}s</span>`;
    const blendedPerM = (m.blended_cost * 1_000_000).toFixed(2);
    const statusCell = m.deployable
      ? `<span class="pill ok">${t("quality.deployable")}</span>`
      : `<span class="pill muted">${t("quality.no_key")}</span>`;
    const actions = m.manual_score != null
      ? `<button class="btn btn-ghost btn-sm reset-override" data-id="${escapeHtml(m.id)}" title="${t("quality.reset_title")}">${escapeHtml(t("common.reset"))}</button>`
      : "";

    tr.innerHTML = `
      <td><code>${escapeHtml(m.id)}</code></td>
      <td>${escapeHtml(m.provider)}</td>
      <td class="num">${aaCell}</td>
      <td class="num">${manualCell}</td>
      <td class="num">${effectiveCell}</td>
      <td class="num">${tpsCell}</td>
      <td class="num">${ttftCell}</td>
      <td class="num">$${blendedPerM}</td>
      <td>${statusCell}</td>
      <td class="th-actions">${actions}</td>
    `;
    tbody.appendChild(tr);
  });

  $$(".set-override").forEach((b) =>
    b.addEventListener("click", () => promptOverride(b.dataset.id, b.dataset.aa))
  );
  $$(".reset-override").forEach((b) =>
    b.addEventListener("click", () => resetOverride(b.dataset.id))
  );
}

function renderQualityPreview() {
  const wrap = $("#quality-preview");
  const body = $("#quality-preview-body");
  if (!state.qualityPreview) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  const p = state.qualityPreview;
  if (!p.primary) {
    body.innerHTML = `<p class="muted">${t("quality.no_deployable")}</p>`;
    return;
  }
  // primary_score is already an int 0-100 from the server (cheapest = null
  // because raw token cost has no meaningful 0-100 mapping).
  const scoreText = p.primary_score != null
    ? `<span class="pill ok">${t("quality.score_fmt", { score: p.primary_score })}</span>`
    : `<span class="pill muted">${t("quality.unscored")}</span>`;
  const fbList = p.fallbacks && p.fallbacks.length
    ? `<div class="small muted">${t("quality.falls_back_fmt", { list: p.fallbacks.map((f) => `<code>${escapeHtml(f)}</code>`).join(", ") })}</div>`
    : "";

  // Per-axis breakdown — surfaces the same numbers the ranker used to
  // decide. Without this, `fastest` looks opaque ("primary X, score 73"
  // tells you nothing about WHY it won). Renders as
  // "tps: raw=145.0 (78/100), ttft: raw=0.41s (88/100)" etc.
  const breakdown = p.primary_score_breakdown || {};
  const breakdownEntries = Object.entries(breakdown);
  const breakdownLine = breakdownEntries.length
    ? `<div class="small muted">${breakdownEntries.map(([axis, vals]) => {
        const raw = vals && vals.raw != null
          ? `${typeof vals.raw === "number" ? vals.raw.toLocaleString(undefined, {maximumFractionDigits: 2}) : escapeHtml(String(vals.raw))}`
          : "—";
        const norm = vals && vals.normalized != null
          ? ` (${(vals.normalized * 100).toFixed(0)}/100)`
          : "";
        return `<code>${escapeHtml(axis)}</code>: ${raw}${norm}`;
      }).join(" · ")}</div>`
    : "";

  body.innerHTML = `
    <div><code>${escapeHtml(p.primary)}</code> ${scoreText}</div>
    <div class="small muted">${t("quality.strategy_prefix")} <code>${escapeHtml(p.strategy)}</code> · ${t("quality.scoring_prefix")} ${escapeHtml(p.scoring_source)}</div>
    ${breakdownLine}
    ${fbList}
  `;
}

async function promptOverride(modelId, aaHint) {
  const seed = aaHint && aaHint !== "" ? aaHint : "";
  const raw = prompt(
    t("quality.prompt_score", { model: modelId })
    + (seed ? `\n\n${t("quality.prompt_aa_hint", { score: seed })}` : ""),
    seed,
  );
  if (raw == null) return;
  const score = Number(raw);
  if (!Number.isFinite(score) || score < 0 || score > 100) {
    toast(t("quality.score_range"), "err");
    return;
  }
  const note = prompt(t("quality.prompt_note"), "") || null;
  try {
    await api(`/v1/quality/overrides/${encodeURIComponent(modelId)}`, {
      method: "PUT",
      body: JSON.stringify({ score, note }),
    });
    toast(t("quality.override_set", { model: modelId }), "ok");
    await Promise.all([loadQuality(), loadQualityPreview()]);
    renderQuality();
    renderQualityPreview();
  } catch (e) {
    toast(e.message, "err");
  }
}

async function resetOverride(modelId) {
  if (!confirm(t("quality.reset_confirm", { model: modelId }))) return;
  try {
    await api(`/v1/quality/overrides/${encodeURIComponent(modelId)}`, { method: "DELETE" });
    toast(t("quality.reset_done", { model: modelId }), "ok");
    await Promise.all([loadQuality(), loadQualityPreview()]);
    renderQuality();
    renderQualityPreview();
  } catch (e) {
    toast(e.message, "err");
  }
}

function bindQualityRefresh() {
  const btn = $("#quality-refresh");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      await api("/v1/quality/refresh", { method: "POST" });
      toast(t("quality.refreshed"), "ok");
      await Promise.all([loadQuality(), loadQualityPreview()]);
      renderQuality();
      renderQualityPreview();
    } catch (e) {
      toast(t("quality.refresh_failed", { msg: e.message }), "err");
    } finally {
      btn.disabled = false;
    }
  });
}

/* ==========================================================================
   MODELS
   ========================================================================== */
async function loadModels() {
  try {
    const data = await api("/v1/models");
    state.models = data.data || [];
  } catch (e) {
    // Non-fatal — overview just shows "—".
    state.models = [];
  }
}

/* ==========================================================================
   OVERVIEW
   ========================================================================== */
function renderOverview() {
  // KPI cards
  const totalReq = (state.spend.by_model || []).reduce((a, m) => a + m.request_count, 0);
  $("#kpi-spend").textContent = fmtUsd(state.spend.total_microcents);
  $("#kpi-spend-sub").textContent = t("overview.across_reqs", { n: fmtNum(totalReq) });
  $("#kpi-saved").textContent = fmtUsd(state.savings.saved_microcents || 0);
  $("#kpi-saved-sub").textContent =
    state.savings.savings_percent
      ? t("overview.vs_gpt4o_off", { pct: state.savings.savings_percent })
      : t("overview.vs_gpt4o_base");

  // Second row: what hosted-auto could save on top of current routing.
  const hostedAuto = state.savings.hosted_auto;
  const haEl = $("#kpi-hosted-auto-value");
  if (haEl) {
    if (hostedAuto && hostedAuto.saved_microcents > 0) {
      haEl.textContent = `+${fmtUsd(hostedAuto.saved_microcents)} (${hostedAuto.savings_percent}%)`;
    } else if (hostedAuto && hostedAuto.comparable_request_count > 0) {
      haEl.textContent = t("overview.already_optimal");
    } else {
      haEl.textContent = "—";
    }
  }

  // True p50/p99 across raw request samples — averaging per-provider
  // percentiles is the "median of medians" trap. The /v1/analytics/latency
  // endpoint only exposes pre-aggregated per-provider values, so we derive
  // global percentiles from the raw latency_ms in /v1/analytics/recent
  // (already loaded into state.recent), using the same algorithm as the
  // backend's _percentile() in app/routes/analytics.py.
  const rawLat = (state.recent || [])
    .map((r) => r.latency_ms)
    .filter((n) => Number.isFinite(n) && n >= 0);
  const p50 = percentile(rawLat, 0.5);
  const p99 = percentile(rawLat, 0.99);
  $("#kpi-p50").textContent = rawLat.length ? `${fmtNum(p50)} ms` : "— ms";
  $("#kpi-p99").textContent = rawLat.length ? `p99 ${fmtNum(p99)} ms` : "p99 — ms";

  $("#kpi-models").textContent = state.models.length ? fmtNum(state.models.length) : "—";
  $("#kpi-providers").textContent = t(
    state.providers.length === 1 ? "overview.provider_1" : "overview.provider_n",
    { n: state.providers.length }
  );

  // Recent mini
  const mini = $("#overview-recent");
  if (!state.recent.length) {
    mini.innerHTML = `<div class="empty-mini">
      <p>${t("analytics.no_requests")}</p>
      <p class="muted">${t("analytics.no_requests_hint")}</p>
    </div>`;
  } else {
    mini.innerHTML = state.recent.slice(0, 5).map((it) => {
      const ok = (it.status_code || 0) < 400;
      return `
        <div class="recent-row">
          <span class="recent-when">${fmtTime(it.created_at)}</span>
          <span class="recent-model">${escapeHtml(it.model_resolved || "—")}</span>
          <span class="recent-latency">${fmtNum(it.latency_ms)} ms</span>
          <span class="pill ${ok ? "ok" : "err"}">${ok ? "OK" : it.status_code}</span>
        </div>`;
    }).join("");
  }
}

/* ─────────────── quickstart snippet ─────────────── */
function snippetFor(lang, baseUrl, key) {
  const k = key && key.startsWith("sk-orca-") ? key : "sk-orca-...";
  if (lang === "node") {
    return `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${baseUrl}",
  apiKey:  "${k}",
});

const r = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(r.choices[0].message.content);`;
  }
  if (lang === "curl") {
    return `curl ${baseUrl}/chat/completions \\
  -H "Authorization: Bearer ${k}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "auto",
    "messages": [{"role":"user","content":"Hello!"}]
  }'`;
  }
  return `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}",
    api_key="${k}",
)

r = client.chat.completions.create(
    model="auto",  # or "gpt-4o-mini", "claude-3-5-sonnet-latest", ...
    messages=[{"role": "user", "content": "Hello!"}],
)
print(r.choices[0].message.content)`;
}

function renderQuickstart() {
  const baseUrl = `${location.origin}/v1`;
  $("#base-url-code").textContent = baseUrl;
  $("#help-base-url").textContent = baseUrl;
  $("#quickstart-code").textContent = snippetFor(state.lang, baseUrl, state.apiKey);
}

function bindQuickstart() {
  $$("#lang-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => {
      $$("#lang-seg .seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.lang = b.dataset.lang;
      renderQuickstart();
    })
  );
  $("#copy-snippet").addEventListener("click", (e) => {
    copyToClipboard($("#quickstart-code").textContent, e.currentTarget);
  });
  $("#copy-base-url").addEventListener("click", () => {
    copyToClipboard(`${location.origin}/v1`);
  });
}

/* ─────────────── onboarding checklist ─────────────── */
function syncOnboarding() {
  const banner = $("#getting-started");
  if (!banner) return;
  if (localStorage.getItem(ONBOARDING_KEY) === "1") {
    banner.classList.add("dismissed");
    return;
  }
  const step1 = state.providers.length > 0;
  const step2 = !!state.routing.strategy;
  const step3 = state.recent.length > 0;
  $("#step-1").classList.toggle("done", step1);
  $("#step-2").classList.toggle("done", step2);
  $("#step-3").classList.toggle("done", step3);
  if (step1 && step2 && step3) {
    setTimeout(() => {
      banner.classList.add("dismissed");
      localStorage.setItem(ONBOARDING_KEY, "1");
    }, 1800);
  }
}

function bindOnboarding() {
  $("#dismiss-getting-started").addEventListener("click", () => {
    localStorage.setItem(ONBOARDING_KEY, "1");
    $("#getting-started").classList.add("dismissed");
  });
}

/* ==========================================================================
   HEALTH POLLING
   ========================================================================== */
async function pollHealth() {
  const dot = $("#health-dot");
  const txt = $("#health-text");
  async function tick() {
    try {
      await api("/health");
      dot.classList.remove("err"); dot.classList.add("ok");
      txt.textContent = t("status.connected");
    } catch {
      dot.classList.remove("ok"); dot.classList.add("err");
      txt.textContent = t("status.disconnected");
    }
  }
  await tick();
  setInterval(tick, 15_000);
}

/* ==========================================================================
   HELP DRAWER
   ========================================================================== */
function openHelp() {
  $("#help-drawer").hidden = false;
  $("#scrim").hidden = false;
}
function closeHelp() {
  const d = $("#help-drawer");
  d.hidden = true;
  $("#scrim").hidden = true;
}
function bindHelp() {
  $("#open-help").addEventListener("click", openHelp);
  $("#close-help").addEventListener("click", closeHelp);
  $("#scrim").addEventListener("click", () => {
    closeHelp();
  });
}

/* ==========================================================================
   COMMAND PALETTE
   ========================================================================== */
function paletteCommands() {
  return [
    { id: "go-overview",  title: t("palette.go_overview"),     meta: t("palette.meta_tab"),  hint: "1",  do: () => setTab("overview")  },
    { id: "go-providers", title: t("palette.go_providers"),    meta: t("palette.meta_tab"),  hint: "2",  do: () => setTab("providers") },
    { id: "go-routing",   title: t("palette.go_routing"),      meta: t("palette.meta_tab"),  hint: "3",  do: () => setTab("routing")   },
    { id: "go-analytics", title: t("palette.go_analytics"),    meta: t("palette.meta_tab"),  hint: "4",  do: () => setTab("analytics") },
    { id: "go-keys",      title: t("palette.go_keys"),         meta: t("palette.meta_tab"),  hint: "5",  do: () => setTab("keys")      },
    { id: "copy-base",    title: t("palette.copy_base"),       meta: t("palette.meta_action"), hint: "", do: () => copyToClipboard(`${location.origin}/v1`) },
    { id: "copy-snip",    title: t("palette.copy_snippet"),    meta: t("palette.meta_action"), hint: "", do: () => copyToClipboard($("#quickstart-code").textContent) },
    { id: "open-help",    title: t("palette.open_help"),       meta: t("palette.meta_help"), hint: "?",  do: () => openHelp() },
    { id: "open-docs",    title: t("palette.open_docs"),       meta: t("palette.meta_link"), hint: "↗", do: () => window.open("https://docs.orcarouter.ai/introduction", "_blank") },
    { id: "open-site",    title: t("palette.open_site"),       meta: t("palette.meta_link"), hint: "↗",  do: () => window.open("https://www.orcarouter.ai", "_blank") },
    { id: "get-hosted-key", title: t("palette.get_hosted_key"), meta: t("palette.meta_link"), hint: "↗", do: () => window.open(state.hosted.token_url || "https://www.orcarouter.ai/console/token", "_blank") },
    { id: "logout",       title: t("palette.logout"),          meta: t("palette.meta_action"), hint: "", do: () => logout() },
  ];
}

let paletteFocus = 0;

function openPalette() {
  $("#palette").hidden = false;
  $("#palette-input").value = "";
  paletteFocus = 0;
  renderPalette("");
  setTimeout(() => $("#palette-input").focus(), 10);
}
function closePalette() { $("#palette").hidden = true; }

function renderPalette(query) {
  const q = query.trim().toLowerCase();
  const all = paletteCommands();
  const items = q ? all.filter((c) => c.title.toLowerCase().includes(q)) : all;
  const list = $("#palette-list");
  if (!items.length) {
    list.innerHTML = `<li class="palette-empty">${t("common.no_matches")}</li>`;
    return;
  }
  list.innerHTML = items.map((c, i) => `
    <li class="palette-item ${i === paletteFocus ? "focused" : ""}" data-id="${c.id}">
      <span>${escapeHtml(c.title)}</span>
      <span class="meta">${escapeHtml(c.hint || c.meta)}</span>
    </li>
  `).join("");
  $$("#palette-list .palette-item").forEach((el) =>
    el.addEventListener("click", () => {
      const cmd = items.find((c) => c.id === el.dataset.id);
      if (cmd) { closePalette(); cmd.do(); }
    })
  );
}

function bindPalette() {
  $("#open-palette").addEventListener("click", openPalette);
  $("#palette-close").addEventListener("click", closePalette);
  const input = $("#palette-input");
  input.addEventListener("input", () => { paletteFocus = 0; renderPalette(input.value); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closePalette();
      return;
    }
    const visible = $$("#palette-list .palette-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      paletteFocus = Math.min(visible.length - 1, paletteFocus + 1);
      renderPalette(input.value);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      paletteFocus = Math.max(0, paletteFocus - 1);
      renderPalette(input.value);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const focused = visible[paletteFocus];
      if (focused) {
        const all = paletteCommands();
        const q = input.value.trim().toLowerCase();
        const items = q ? all.filter((c) => c.title.toLowerCase().includes(q)) : all;
        const cmd = items.find((c) => c.id === focused.dataset.id);
        if (cmd) { closePalette(); cmd.do(); }
      }
    }
  });
  // click on the backdrop (anywhere outside the card) closes
  $("#palette").addEventListener("click", (e) => {
    if (!e.target.closest(".palette-card")) closePalette();
  });
}

/* ==========================================================================
   LOGOUT
   ========================================================================== */
function logout() {
  localStorage.removeItem(KEY_STORAGE);
  state.apiKey = "";
  showGate();
  toast(t("auth.signed_out"), "info");
}

/* ==========================================================================
   GLOBAL KEYBOARD SHORTCUTS
   ========================================================================== */
function bindKeyboard() {
  document.addEventListener("keydown", (e) => {
    const inField = e.target.matches("input, textarea, [contenteditable=true]");
    const cmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";

    if (cmdK) {
      e.preventDefault();
      if ($("#palette").hidden) openPalette(); else closePalette();
      return;
    }
    if (e.key === "Escape") {
      if (!$("#palette").hidden) closePalette();
      else if (!$("#help-drawer").hidden) closeHelp();
      return;
    }
    if (inField) return;
    if ($("#auth-gate").hidden === false) return;

    if (e.key === "?") { e.preventDefault(); $("#help-drawer").hidden ? openHelp() : closeHelp(); }
    if (e.key >= "1" && e.key <= "5") {
      const order = ["overview", "providers", "routing", "analytics", "keys"];
      const idx = parseInt(e.key, 10) - 1;
      if (order[idx]) setTab(order[idx]);
    }
  });
}

/* ==========================================================================
   AUTH FORM BIND
   ========================================================================== */
function bindAuth() {
  const form = $("#auth-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = $("#api-key-input").value.trim();
    if (!v) return;
    state.apiKey = v;
    localStorage.setItem(KEY_STORAGE, v);
    const status = $("#auth-status");
    status.textContent = t("auth.checking");
    status.classList.remove("ok");
    const ok = await checkAuth();
    if (ok) {
      status.textContent = t("auth.welcome_aboard");
      status.classList.add("ok");
      setTimeout(showShell, 350);
    } else {
      status.textContent = t("auth.key_invalid");
      localStorage.removeItem(KEY_STORAGE);
      state.apiKey = "";
    }
  });

  $("#api-key-toggle").addEventListener("click", () => {
    const i = $("#api-key-input");
    i.type = i.type === "password" ? "text" : "password";
  });

  $("#logout-btn").addEventListener("click", logout);
}

/* ==========================================================================
   BOOT
   ========================================================================== */
document.addEventListener("DOMContentLoaded", async () => {
  state.locale = detectLocale();
  applyI18n();
  bindLocalePicker();
  bindAuth();
  bindTabs();
  renderProviderOptions();
  bindProviderForm();
  bindRouting();
  bindWindowSeg();
  bindKeyForm();
  bindQualityRefresh();
  bindHelp();
  bindPalette();
  bindKeyboard();
  bindQuickstart();
  bindOnboarding();
  bindHostedForm();

  // Probe existing key
  const ok = await checkAuth();
  if (ok) showShell();
  else showGate();
});

window.addEventListener("hashchange", () => {
  const t = (location.hash || "").replace("#", "");
  if (TAB_META[t]) setTab(t);
});
