import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// Exercise the real extensions against a minimal DOM and an in-memory HTTP API.
class Element {
    constructor(tag) {
        this.tagName = tag;
        this.children = [];
        this.style = { setProperty() {} };
        this.classList = { add() {}, remove() {}, toggle() {} };
        this.dataset = {};
        this.value = "";
    }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.append(item); return item; }
    insertBefore(item) { this.children.unshift(item); }
    replaceChildren(...items) { this.children = items; }
    addEventListener() {}
    removeEventListener() {}
    setAttribute() {}
    removeAttribute() {}
    querySelector() { return new Element("span"); }
    querySelectorAll() { return []; }
    remove() {}
    blur() {}
    focus() {}
}
const elements = [];
const calls = [];
let extension;
const signal = { aborted: false, addEventListener() {} };
const context = vm.createContext({
    console, URL, setTimeout, clearTimeout,
    document: {
        createElement: tag => { const el = new Element(tag); elements.push(el); return el; },
        createDocumentFragment: () => new Element("fragment"),
        getElementById: () => null,
        addEventListener() {},
        head: new Element("head"), body: new Element("body"),
    },
    localStorage: { getItem: () => null, setItem() {} },
    window: { setTimeout, clearTimeout },
    requestAnimationFrame: fn => fn(),
    addPanel: () => ({ signal }),
    addDeleteButton() {},
    api: {
        addEventListener() {}, removeEventListener() {},
        async fetchApi(url) {
            calls.push(url);
            await Promise.resolve();
            return { ok: true, json: async () => ({ projects: [], clips: [] }) };
        },
    },
    app: { registerExtension(value) { extension = value; } },
});
for (const file of ["project_menu.js", "clip_bin_picker.js"]) {
    const source = readFileSync(new URL(`../../web/${file}`, import.meta.url), "utf8")
        .replace(/^import .*;\r?\n/gm, "")
        .replace("export function createProjectMenu", "function createProjectMenu")
        .replaceAll("import.meta.url", JSON.stringify("file:///clipstream/web/clip_bin_picker.js"));
    vm.runInContext(source, context, { filename: file });
}
function node() {
    return {
        size: [680, 640],
        widgets: [{ name: "project_name", value: "Mixed Project" },
                  { name: "clip_selection", value: "latest" },
                  { name: "mode", value: "Auto" }],
        setSize(size) { this.size = size; },
        setDirtyCanvas() {},
    };
}
for (const name of ["MiniMaxClipBinPicker", "MiniMaxClipBinDualPicker"]) {
    class Node {}
    await extension.beforeRegisterNodeDef(Node, { name });
    Node.prototype.onNodeCreated.call(node());
}
await new Promise(resolve => setTimeout(resolve, 0));
for (const kind of ["single", "dual"]) {
    assert.ok(calls.includes(`/minimax/clip_bin/projects?asset_kind=${kind}`), `project menu scopes ${kind}`);
    assert.ok(calls.includes(`/minimax/clip_bin/list?project=Mixed%20Project&asset_kind=${kind}`), `gallery scopes ${kind}`);
}
assert.equal(calls.filter(url => url.startsWith("/minimax/clip_bin/projects?")).length, 2,
             "concurrent single and dual menus must not share a response");
vm.runInContext("createProjectMenu({ node: testNode, widget: testNode.widgets[0], signal: testSignal, mode: 'builder' })",
                Object.assign(context, { testNode: node(), testSignal: signal }));
await new Promise(resolve => setTimeout(resolve, 0));
assert.ok(calls.includes("/minimax/clip_bin/projects?videos_only=1"), "Builder keeps its unfiltered video menu");
for (const kind of ["single", "dual"]) {
    const selected = node();
    const menu = vm.runInContext("createProjectMenu({ node: testNode, widget: testNode.widgets[0], signal: testSignal, mode: 'picker', assetKind: testKind })",
        Object.assign(context, { testNode: selected, testSignal: signal, testKind: kind }));
    await menu.refresh();
    const current = elements.filter(el => el.className === "minimax-project-current").at(-1);
    current.onclick({ preventDefault() {}, stopPropagation() {} });
    const grid = elements.filter(el => el.className === "minimax-project-grid").at(-1);
    assert.equal(grid.children[0]?.className, "minimax-project-empty", `${kind} does not reinsert the active empty project`);
    assert.equal(selected.widgets[0].value, "Mixed Project", "hidden project remains selected for initial generation");
}
console.log("Picker isolation UI: 10 assertions passed");
