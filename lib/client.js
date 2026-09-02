window.__ModuleLoader__.load({ id: 'dsh-researchcraft', factory: (require) => { var module = { exports: {} }; var exports = module.exports;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// client/index.js
var index_exports = {};
__export(index_exports, {
  apply: () => apply,
  inject: () => inject
});
module.exports = __toCommonJS(index_exports);

// client/ApiKeysSection.jsx
var import_react = require("react");
var import_jsx_runtime = require("react/jsx-runtime");
var IMAGE_MODEL_OPTIONS = [
  { value: "gemini-2.5-flash-image", label: "gemini-2.5-flash-image \u2014 nano banana" },
  { value: "gemini-3.1-flash-image", label: "gemini-3.1-flash-image \u2014 nano banana 2" },
  { value: "gemini-3-pro-image", label: "gemini-3-pro-image \u2014 nano banana pro" }
];
var SUBAGENT_MODEL_COMPLEX_OPTIONS = [
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro (default)" }
];
var SUBAGENT_MODEL_VISION_OPTIONS = [
  { value: "deepseek-v4-flash-vision-exp", label: "deepseek-v4-flash-vision-exp (default)" }
];
var CUSTOM_MODEL = "__custom__";
var KEYS = [
  { field: "PARALLEL_API_KEY", label: "Parallel", group: "Literature search", hint: "Required for mcp__parallel__* and parallel_search \u2014 sent as a Bearer token so search is not rate-limited. Restart dsh after saving." },
  { field: "FIRECRAWL_API_KEY", label: "Firecrawl", group: "Literature search", hint: "Optional \u2014 raises the keyless rate limit." },
  { field: "CONSENSUS_API_KEY", label: "Consensus", group: "Literature search", hint: "Required to enable this connector." },
  { field: "SCITE_API_KEY", label: "Scite", group: "Literature search", hint: "Required to enable this connector." },
  { field: "UNPAYWALL_EMAIL", label: "Unpaywall contact email", group: "Literature search", hint: "Required for paper_download to resolve a DOI to an open-access PDF \u2014 Unpaywall asks API callers to identify themselves with a real email." },
  { field: "GEMINI_API_KEY", label: "Gemini", group: "Image generation", hint: "Enables the image_generate tool." },
  { field: "IMAGE_MODEL", label: "Image model", group: "Image generation", type: "select", options: IMAGE_MODEL_OPTIONS, hint: "Which Gemini model image_generate uses by default. Defaults to nano banana if unset." },
  { field: "SUBAGENT_MODEL_COMPLEX", label: "Complex-task model", group: "Subagent model routing", type: "select", options: SUBAGENT_MODEL_COMPLEX_OPTIONS, hint: "Model for the subagent_pro delegation tool (unusually heavy reasoning). Requires restarting dsh to apply \u2014 same as the MCP connector keys above, not like Image model." },
  { field: "SUBAGENT_MODEL_VISION", label: "Image-reading model", group: "Subagent model routing", type: "select", options: SUBAGENT_MODEL_VISION_OPTIONS, hint: "Model for the subagent_vision delegation tool (reads images via read_image). Requires restarting dsh to apply \u2014 same as the MCP connector keys above, not like Image model." },
  { field: "MODAL_TOKEN_ID", label: "Modal \u2014 token ID", group: "Remote compute", hint: "From modal.com/settings." },
  { field: "MODAL_TOKEN_SECRET", label: "Modal \u2014 token secret", group: "Remote compute", hint: "From modal.com/settings." },
  { field: "RUNPOD_API_KEY", label: "Runpod", group: "Remote compute", hint: "From console.runpod.io/user/settings." }
];
var GROUPS = [...new Set(KEYS.map((k) => k.group))];
var errorText = { color: "var(--color-danger, #c0392b)", margin: 0, fontSize: "0.85em" };
var hintText = { margin: 0, opacity: 0.6, fontSize: "0.8em" };
var fieldLabel = { fontSize: "0.85em" };
function SelectField({ k, scope, snapshot, writable }) {
  const stored = snapshot.value?.[k.field] || "";
  const known = k.options.some((o) => o.value === stored);
  const [customMode, setCustomMode] = (0, import_react.useState)(Boolean(stored) && !known);
  const [customDraft, setCustomDraft] = (0, import_react.useState)(known ? "" : stored);
  const [busy, setBusy] = (0, import_react.useState)(false);
  const [error, setError] = (0, import_react.useState)();
  const apply2 = async (value) => {
    setBusy(true);
    setError(void 0);
    try {
      if (value) await scope.set(k.field, value);
      else await scope.unset(k.field);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const onSelectChange = (e) => {
    const value = e.target.value;
    if (value === CUSTOM_MODEL) {
      setCustomMode(true);
      return;
    }
    setCustomMode(false);
    apply2(value);
  };
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "0.25rem" }, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { style: fieldLabel, children: [
      k.label,
      " \u2014 ",
      stored || `default (${k.options[0].value})`
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
      "select",
      {
        value: customMode ? CUSTOM_MODEL : stored || k.options[0].value,
        disabled: busy || !writable,
        onChange: onSelectChange,
        style: { flex: 1 },
        children: [
          k.options.map((o) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: o.value, children: o.label }, o.value)),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: CUSTOM_MODEL, children: "Custom\u2026" })
        ]
      }
    ),
    customMode && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: "0.5rem" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        "input",
        {
          type: "text",
          autoComplete: "off",
          placeholder: "model id, e.g. gemini-2.0-flash-exp",
          value: customDraft,
          disabled: busy || !writable,
          onChange: (e) => setCustomDraft(e.target.value),
          style: { flex: 1 }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", disabled: busy || !writable || !customDraft.trim(), onClick: () => apply2(customDraft.trim()), children: "Apply" })
    ] }),
    error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: errorText, children: error }),
    k.hint && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: hintText, children: k.hint })
  ] }, k.field);
}
function SecretField({ k, scope, snapshot, writable }) {
  const [draft, setDraft] = (0, import_react.useState)("");
  const [busy, setBusy] = (0, import_react.useState)(false);
  const [error, setError] = (0, import_react.useState)();
  const configured = Boolean(snapshot.value?.[k.field]);
  const save = async () => {
    const value = draft.trim();
    if (!value) return;
    setBusy(true);
    setError(void 0);
    try {
      await scope.set(k.field, value);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const clear = async () => {
    setBusy(true);
    setError(void 0);
    try {
      await scope.unset(k.field);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "0.25rem" }, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { style: fieldLabel, children: [
      k.label,
      " \u2014 ",
      configured ? "configured" : "not set"
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: "0.5rem" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        "input",
        {
          type: "password",
          autoComplete: "off",
          placeholder: configured ? "leave blank to keep" : "not set",
          value: draft,
          disabled: busy || !writable,
          onChange: (e) => setDraft(e.target.value),
          style: { flex: 1 }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", disabled: busy || !writable || !draft.trim(), onClick: save, children: "Save" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", disabled: busy || !writable || !configured, onClick: clear, children: "Clear" })
    ] }),
    error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: errorText, children: error }),
    k.hint && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: hintText, children: k.hint })
  ] }, k.field);
}
function ApiKeysSection(props) {
  const { scope } = props;
  const [snapshot, setSnapshot] = (0, import_react.useState)(() => scope.getSnapshot());
  (0, import_react.useEffect)(() => scope.subscribe(() => setSnapshot(scope.getSnapshot())), [scope]);
  if (snapshot.status === "loading") {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { padding: "4px 0" }, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "Connecting\u2026" }) });
  }
  if (snapshot.status === "unavailable") {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { padding: "4px 0" }, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "Settings storage is unavailable in this browser session (non-loopback connections don't get durable settings). Set the matching environment variables before starting DSH instead." }) });
  }
  const writable = snapshot.writable !== false;
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "1.5rem", padding: "4px 0" }, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "API keys for ResearchCraft's academic-search connectors, image generation, and remote-compute tools. A key set here is used only when the matching environment variable isn't already set when DSH starts." }),
    !writable && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: errorText, children: "Settings storage is read-only in this session." }),
    GROUPS.map((group) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "0.75rem" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { style: { margin: 0, fontSize: "0.95em" }, children: group }),
      KEYS.filter((k) => k.group === group).map((k) => k.type === "select" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SelectField, { k, scope, snapshot, writable }, k.field) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SecretField, { k, scope, snapshot, writable }, k.field))
    ] }, group))
  ] });
}

// client/index.js
var NAMESPACE = "dsh-researchcraft-keys";
var inject = ["slots", "settingsScope"];
function apply(ctx) {
  const scope = ctx.settingsScope.bind({ namespace: NAMESPACE });
  ctx.slots.inject("settings.section", () => ctx.slots.register({
    name: "settings.section",
    id: "researchcraft-api-keys",
    order: 60,
    label: () => "ResearchCraft API keys",
    inject: () => ({ scope })
  }, ApiKeysSection));
}
return module.exports; } });
//# sourceMappingURL=client.js.map
