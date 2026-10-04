// Card sizing rules for the Long Builder panel. Run with:
//   node tests/js/long_builder_fit.test.mjs
//
// The panel measures the live DOM and calls these functions; this file pins the rules
// themselves, because the failure mode is a deck that jumps to one endless row or runs off
// the screen at some zoom - which no browser-free node test can catch.
//
// The rule being pinned: zoom changes the cards, never the width, and keeps the rows.
import test from "node:test";
import assert from "node:assert/strict";
import {
    DECK_PAD_V,
    MAX_ROWS,
    cardMinFor,
    clampIndex,
    columnsFor,
    heightForRowCount,
    planFitHeight,
    planZoomHeight,
    rowHeightFor,
    stepIndex,
    thumbHeightFor,
    visibleRows,
    zoomPercent,
} from "../../web/long_builder_fit.js";

const screen = { viewHeight: 2000 };
const chrome = { chromeHeight: 220 };

test("the zoom steps are 100% to 400% and cannot run off either end", () => {
    assert.deepEqual([0, 1, 2, 3, 4].map(zoomPercent), [100, 150, 200, 300, 400]);
    assert.equal(cardMinFor(0), 150);
    assert.equal(cardMinFor(4), 600);
    assert.equal(thumbHeightFor(4), 340);
    assert.equal(clampIndex(-3), 0);
    assert.equal(clampIndex(99), 4);
    assert.equal(clampIndex("not a number"), 0);
    assert.equal(stepIndex(3, 1), 4);
    assert.equal(stepIndex(0, -1), 0);
});

test("columns follow the grid rule", () => {
    assert.equal(columnsFor(610, 150), 3);
    assert.equal(columnsFor(640, 150), 4);
    assert.equal(columnsFor(300, 150), 1);
    assert.equal(columnsFor(0, 150), 0);
    assert.equal(columnsFor(1200, 600), 1);
});

test("only whole rows count as visible", () => {
    assert.equal(visibleRows(310, 150), 2);
    assert.equal(visibleRows(150, 150), 1);
    assert.equal(visibleRows(149, 150), 0, "a card cut in half is not a row");
    assert.equal(visibleRows(0, 150), 0);
    assert.equal(visibleRows(400, 0), 0);
});

test("a row count turns into a deck height with the gaps", () => {
    assert.equal(heightForRowCount(1, 150), 150);
    assert.equal(heightForRowCount(2, 150), 310);
    assert.equal(heightForRowCount(3, 150), 470);
    assert.equal(heightForRowCount(0, 150), 0);
});

test("zooming in keeps the rows and grows by the row-height difference", () => {
    const twoRows = heightForRowCount(2, 150);
    assert.equal(planZoomHeight({
        deckHeight: twoRows, rowHeightBefore: 150, rowHeightAfter: 300, ...chrome, ...screen,
    }), heightForRowCount(2, 300));
});

test("zooming out shrinks the deck and still keeps the rows", () => {
    const twoRows = heightForRowCount(2, 150);
    const after = planZoomHeight({
        deckHeight: twoRows, rowHeightBefore: 150, rowHeightAfter: 75, ...chrome, ...screen,
    });
    assert.equal(after, heightForRowCount(2, 75));
    assert.ok(after < twoRows, "smaller cards, smaller node - the width is not touched");
});

test("a deck that showed one row keeps showing one row", () => {
    assert.equal(planZoomHeight({
        deckHeight: 150, rowHeightBefore: 150, rowHeightAfter: 600, ...chrome, ...screen,
    }), heightForRowCount(1, 600));
});

test("a big zoom is capped by the screen, but one row always survives", () => {
    const small = { viewHeight: 600 };
    const wanted = planZoomHeight({
        deckHeight: heightForRowCount(2, 150), rowHeightBefore: 150, rowHeightAfter: 300,
        ...chrome, ...small,
    });
    assert.equal(wanted, 600 - chrome.chromeHeight, "the node stays inside the screen");
    assert.ok(wanted >= heightForRowCount(1, 300), "and one whole card is still visible");
    const tiny = { viewHeight: 200 };
    assert.equal(planZoomHeight({
        deckHeight: 150, rowHeightBefore: 150, rowHeightAfter: 300, ...chrome, ...tiny,
    }), heightForRowCount(1, 300), "never less than one row, even off-screen");
});

test("the fit button fills the width it has, at most two rows", () => {
    const wanted = planFitHeight({ count: 12, deckWidth: 640, zoomIdx: 0, rowHeight: 150, ...chrome, ...screen });
    assert.equal(columnsFor(640, cardMinFor(0)), 4);
    assert.equal(wanted, heightForRowCount(MAX_ROWS, 150));
});

test("a narrow width still stops at two rows and scrolls the rest", () => {
    const wanted = planFitHeight({ count: 12, deckWidth: 300, zoomIdx: 0, rowHeight: 150, ...chrome, ...screen });
    assert.equal(columnsFor(300, cardMinFor(0)), 1);
    assert.equal(wanted, heightForRowCount(MAX_ROWS, 150), "not twelve rows");
});

test("a short deck does not ask for empty space", () => {
    assert.equal(planFitHeight({ count: 1, deckWidth: 640, zoomIdx: 0, rowHeight: 150, ...chrome, ...screen }),
        heightForRowCount(1, 150));
});

test("an empty bin leaves the area alone", () => {
    assert.equal(planFitHeight({ count: 0, deckWidth: 640, zoomIdx: 2, rowHeight: 150, ...chrome, ...screen }), 0);
});

test("the deck box includes its own padding", () => {
    const wanted = planFitHeight({
        count: 12, deckWidth: 640, zoomIdx: 0, rowHeight: 150, padV: DECK_PAD_V, ...chrome, ...screen,
    });
    assert.equal(wanted, heightForRowCount(MAX_ROWS, 150) + DECK_PAD_V,
        "the panel measures the deck box, so the plan has to include it");
});

test("padding is capped by the screen, but a padded row still survives", () => {
    const small = { viewHeight: 600 };
    const wanted = planZoomHeight({
        deckHeight: heightForRowCount(2, 150), rowHeightBefore: 150, rowHeightAfter: 300,
        padV: DECK_PAD_V, ...chrome, ...small,
    });
    assert.equal(wanted, 600 - chrome.chromeHeight);
    const tiny = { viewHeight: 200 };
    assert.equal(planZoomHeight({
        deckHeight: 150, rowHeightBefore: 150, rowHeightAfter: 300,
        padV: DECK_PAD_V, ...chrome, ...tiny,
    }), heightForRowCount(1, 300) + DECK_PAD_V, "one whole card, padding included");
});

test("the row height falls back to the zoom, not to a fixed size", () => {
    const small = planFitHeight({ count: 20, deckWidth: 1200, zoomIdx: 0, ...chrome, ...screen });
    const huge = planFitHeight({ count: 20, deckWidth: 1200, zoomIdx: 4, ...chrome, ...screen });
    assert.equal(small, heightForRowCount(2, rowHeightFor(0)));
    assert.equal(huge, heightForRowCount(2, rowHeightFor(4)));
    assert.ok(huge > small);
});
