import test from "node:test";
import assert from "node:assert/strict";
import {
    normalizeCustomSpeed,
    outputFrameRate,
    outputPlaybackSpeed,
    restoredDuration,
    sourcePlaybackSpeed,
    speedDescription,
    speedOptionLabel,
} from "../../web/long_builder_speed.js";

test("presets mirror the cutting nodes", () => {
    assert.equal(sourcePlaybackSpeed("1.0x"), 1);
    assert.equal(sourcePlaybackSpeed("0.75x"), 0.75);
    assert.equal(sourcePlaybackSpeed("0.5x"), 0.5);
});

test("custom speed is clamped and rounded to one decimal", () => {
    assert.equal(normalizeCustomSpeed(0.62), 0.6);
    assert.equal(normalizeCustomSpeed(0), 0.1);
    assert.equal(normalizeCustomSpeed(1.2), 1);
    assert.equal(normalizeCustomSpeed("bad", 0.8), 0.8);
});

test("builder restores the reciprocal output speed and duration", () => {
    assert.equal(outputPlaybackSpeed("0.5x"), 2);
    assert.ok(Math.abs(outputPlaybackSpeed("0.75x") - 4 / 3) < 1e-9);
    assert.equal(restoredDuration(12, "0.5x"), 6);
    assert.equal(restoredDuration(12, "1.0x"), 12);
});

test("output frame rate keeps rendered frames when speed is restored", () => {
    assert.equal(outputFrameRate(24, "1.0x"), 24);
    assert.equal(outputFrameRate(24, "0.5x"), 48);
    assert.equal(outputFrameRate(24, "0.75x"), 32);
    assert.equal(outputFrameRate(24, "custom", 0.1), 240);
    assert.equal(outputFrameRate("bad", "0.5x"), 0);
});

test("labels explain the result without mental arithmetic", () => {
    assert.equal(speedOptionLabel("0.5x"), "0.5x → 2x");
    assert.match(speedDescription("0.75x", 1.0, 24), /1\.333x/);
    assert.match(speedDescription("0.75x", 1.0, 24), /32\.000fps/);
    assert.match(speedDescription("0.5x", 1.0, 24), /48\.000fps/);
    assert.match(speedDescription("1.0x"), /无损直拷/);
});
