"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const context = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "macip_filter.js"), "utf8"), context);
const {navigateOwnName} = context.MacipFilter;

const rows = Array.from({length: 3}, () => ({}));
const inputs = rows.map(row => ({
  disabled: false,
  focused: false,
  closest: selector => selector === "tr" ? row : null,
  focus() { this.focused = true; }
}));
rows.forEach((row, i) => {
  row.previousElementSibling = rows[i - 1] || null;
  row.nextElementSibling = rows[i + 1] || null;
  row.querySelector = () => inputs[i].disabled ? null : inputs[i];
});

function check(index, key, options, expected) {
  inputs.forEach(input => { input.focused = false; });
  let prevented = false;
  navigateOwnName({
    currentTarget: inputs[index], key, ...options,
    preventDefault() { prevented = true; }
  });
  assert.equal(prevented, expected !== null, `${key}: default handling`);
  assert.deepEqual(inputs.map(input => input.focused),
    inputs.map((_, i) => i === expected), `${key}: focused input`);
}

check(0, "Enter", {}, 1);
check(1, "Enter", {shiftKey: true}, 0);
check(1, "ArrowUp", {}, 0);
check(1, "ArrowDown", {}, 2);
check(0, "Tab", {}, 1);
check(2, "Tab", {shiftKey: true}, 1);
check(2, "Tab", {}, null);
check(0, "Tab", {shiftKey: true}, null);
check(1, "ArrowDown", {shiftKey: true}, null);
check(1, "ArrowDown", {ctrlKey: true}, null);
check(1, "Enter", {isComposing: true}, null);
check(1, "ArrowLeft", {}, null);
inputs[1].disabled = true;
check(0, "Enter", {}, 2);

console.log("OK: own-name keyboard navigation");
