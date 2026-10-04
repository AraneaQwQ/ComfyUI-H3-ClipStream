// Deck-order rules for the Long Builder panel. Run with:
//   node tests/js/long_builder_order.test.mjs
//
// tests/test_long_builder.py covers the same rules on the node side. This file covers
// the copy the panel uses, because a deck that shows one order while the node joins
// another is the one failure this feature has to avoid.
import test from "node:test";
import assert from "node:assert/strict";
import { moveCard, resolveDeckOrder } from "../../web/long_builder_order.js";

const none = new Set();
const card = (clipId, shot, extra = {}) => ({ clip_id: clipId, shot_tag: shot, has_video: true, ...extra });
const ids = deck => deck.map(card2 => card2.clip_id);

test("the deck follows the shot numbers", () => {
    const cards = [card("clip_c3", "Shot 3"), card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2")];
    assert.deepEqual(resolveDeckOrder(cards, "", none).joinIds, ["clip_c1", "clip_c2", "clip_c3"]);
});

test("Shot 12 comes after Shot 2", () => {
    const cards = [card("clip_b", "Shot 12"), card("clip_a", "Shot 2")];
    assert.deepEqual(resolveDeckOrder(cards, "", none).joinIds, ["clip_a", "clip_b"]);
});

test("the dragged order wins, and unlisted cards are appended by shot number", () => {
    const cards = [card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2"), card("clip_c3", "Shot 3")];
    assert.deepEqual(resolveDeckOrder(cards, "clip_c3,clip_c1", none).joinIds,
        ["clip_c3", "clip_c1", "clip_c2"]);
});

test("a shot tag in the order resolves to the same card", () => {
    const cards = [card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2")];
    assert.deepEqual(resolveDeckOrder(cards, "Shot 2, Shot 1", none).joinIds,
        ["clip_c2", "clip_c1"]);
});

test("a reference whose card was deleted is ignored", () => {
    const cards = [card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2")];
    assert.deepEqual(resolveDeckOrder(cards, "clip_gone,clip_c2", none).joinIds,
        ["clip_c2", "clip_c1"]);
});

test("cards that cannot join stay out of the order and at the end of the deck", () => {
    const cards = [card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2", { has_video: false }),
        card("clip_c3", "Shot 3")];
    const { deck, joinIds } = resolveDeckOrder(cards, "", new Set(["clip_c3"]));
    assert.deepEqual(joinIds, ["clip_c1"]);
    assert.deepEqual(ids(deck), ["clip_c1", "clip_c2", "clip_c3"]);
});

test("the joining cards are always the first cards in the deck", () => {
    // The panel numbers the cards from this invariant, and the node joins in this order.
    const cards = [card("clip_c1", "Shot 1"), card("clip_c2", "Shot 2", { has_video: false }),
        card("clip_c3", "Shot 3"), card("clip_c4", "Shot 4")];
    const { deck, joinIds } = resolveDeckOrder(cards, "clip_c4", new Set(["clip_c3"]));
    assert.deepEqual(ids(deck).slice(0, joinIds.length), joinIds);
});

test("moveCard puts a card before or after the card under the pointer", () => {
    assert.deepEqual(moveCard(["a", "b", "c", "d"], "d", "b", false), ["a", "b", "d", "c"]);
    assert.deepEqual(moveCard(["a", "b", "c", "d"], "a", "c", true), ["b", "a", "c", "d"]);
});

test("moving a card onto itself or onto an unknown card changes nothing", () => {
    assert.deepEqual(moveCard(["a", "b", "c"], "b", "b", true), ["a", "b", "c"]);
    assert.deepEqual(moveCard(["a", "b", "c"], "x", "a", true), ["a", "b", "c"]);
});
