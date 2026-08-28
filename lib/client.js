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
var KEYS = [
  { field: "PARALLEL_API_KEY", label: "Parallel", group: "Literature search", hint: "Optional \u2014 raises the keyless rate limit." },
  { field: "FIRECRAWL_API_KEY", label: "Firecrawl", group: "Literature search", hint: "Optional \u2014 raises the keyless rate limit." },
  { field: "CONSENSUS_API_KEY", label: "Consensus", group: "Literature search", hint: "Required to enable this connector." },
  { field: "SCITE_API_KEY", label: "Scite", group: "Literature search", hint: "Required to enable this connector." },
  { field: "GEMINI_API_KEY", label: "Gemini (nano banana)", group: "Image generation", hint: "Enables the image_generate tool." },
  { field: "MODAL_TOKEN_ID", label: "Modal \u2014 token ID", group: "Remote compute", hint: "From modal.com/settings." },
  { field: "MODAL_TOKEN_SECRET", label: "Modal \u2014 token secret", group: "Remote compute", hint: "From modal.com/settings." },
  { field: "RUNPOD_API_KEY", label: "Runpod", group: "Remote compute", hint: "From console.runpod.io/user/settings." }
];
var GROUPS = [...new Set(KEYS.map((k) => k.group))];
function ApiKeysSection(props) {
  const { scope } = props;
  const [snapshot, setSnapshot] = (0, import_react.useState)(() => scope.getSnapshot());
  const [drafts, setDrafts] = (0, import_react.useState)({});
  const [busy, setBusy] = (0, import_react.useState)({});
  const [errors, setErrors] = (0, import_react.useState)({});
  (0, import_react.useEffect)(() => scope.subscribe(() => setSnapshot(scope.getSnapshot())), [scope]);
  if (snapshot.status === "loading") {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { padding: "4px 0" }, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "Connecting\u2026" }) });
  }
  if (snapshot.status === "unavailable") {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { padding: "4px 0" }, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "Settings storage is unavailable in this browser session (non-loopback connections don't get durable settings). Set the matching environment variables before starting DSH instead." }) });
  }
  const writable = snapshot.writable !== false;
  const isConfigured = (field) => Boolean(snapshot.value?.[field]);
  const save = async (field) => {
    const value = (drafts[field] ?? "").trim();
    if (!value) return;
    setBusy((b) => ({ ...b, [field]: true }));
    setErrors((e) => ({ ...e, [field]: void 0 }));
    try {
      await scope.set(field, value);
      setDrafts((d) => ({ ...d, [field]: "" }));
    } catch (error) {
      setErrors((e) => ({ ...e, [field]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy((b) => ({ ...b, [field]: false }));
    }
  };
  const clear = async (field) => {
    setBusy((b) => ({ ...b, [field]: true }));
    setErrors((e) => ({ ...e, [field]: void 0 }));
    try {
      await scope.unset(field);
    } catch (error) {
      setErrors((e) => ({ ...e, [field]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy((b) => ({ ...b, [field]: false }));
    }
  };
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "1.5rem", padding: "4px 0" }, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.75, fontSize: "0.9em" }, children: "API keys for ResearchCraft's academic-search connectors, image generation, and remote-compute tools. A key set here is used only when the matching environment variable isn't already set when DSH starts." }),
    !writable && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { color: "var(--color-danger, #c0392b)", margin: 0, fontSize: "0.85em" }, children: "Settings storage is read-only in this session." }),
    GROUPS.map((group) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "0.75rem" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { style: { margin: 0, fontSize: "0.95em" }, children: group }),
      KEYS.filter((k) => k.group === group).map((k) => {
        const configured = isConfigured(k.field);
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: "0.25rem" }, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { style: { fontSize: "0.85em" }, children: [
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
                value: drafts[k.field] ?? "",
                disabled: Boolean(busy[k.field]) || !writable,
                onChange: (e) => setDrafts((d) => ({ ...d, [k.field]: e.target.value })),
                style: { flex: 1 }
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                disabled: Boolean(busy[k.field]) || !writable || !drafts[k.field]?.trim(),
                onClick: () => save(k.field),
                children: "Save"
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                disabled: Boolean(busy[k.field]) || !writable || !configured,
                onClick: () => clear(k.field),
                children: "Clear"
              }
            )
          ] }),
          errors[k.field] && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { color: "var(--color-danger, #c0392b)", margin: 0, fontSize: "0.85em" }, children: errors[k.field] }),
          k.hint && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, opacity: 0.6, fontSize: "0.8em" }, children: k.hint })
        ] }, k.field);
      })
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
