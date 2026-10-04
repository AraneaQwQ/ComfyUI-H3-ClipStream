// Deck order for the Long Builder: the order of the cards IS the order of the film.
//
// Kept apart from the panel and free of ComfyUI imports so it can be read on its own
// and exercised by `node tests/js/long_builder_order.test.mjs`. The panel asks for the
// cards to show and, after a drag, the new list of clip_ids to write into the node.
// The rules here mirror clipbin/long_builder.py: shot number by default, the dragged
// order when there is one, and anything the dragged order does not mention appended by
// shot number so a segment generated after the last drag still shows up.

// Same separators as long_builder.parse_sequence.
export function parseOrder(text) {
    return String(text || "").split(/[,;\n]+/).map(part => part.trim()).filter(Boolean);
}

// Mirrors long_builder.shot_number: the first number in a tag is the timeline position.
export function shotNumber(tag) {
    const match = /(\d+)/.exec(String(tag || ""));
    return match ? parseInt(match[1], 10) : null;
}

// Mirrors long_builder.shot_sort_key: numbered cards first, then generation order.
export function sortCards(cards) {
    return [...(cards || [])].sort((a, b) => {
        const na = shotNumber(a.shot_tag);
        const nb = shotNumber(b.shot_tag);
        if ((na === null) !== (nb === null)) return na === null ? 1 : -1;
        if (na !== null && nb !== null && na !== nb) return na - nb;
        return String(a.created_at || "").localeCompare(String(b.created_at || ""))
            || String(a.clip_id || "").localeCompare(String(b.clip_id || ""));
    });
}

// A card joins the film when it has an archived video and was not switched off.
export function isJoinable(card, excludedIds) {
    return Boolean(card.has_video) && !excludedIds.has(String(card.clip_id));
}

// Mirrors long_builder.find_clip: exact clip_id first, then a substring of either id
// or shot tag, so a hand-written order still resolves.
function findCard(cards, reference) {
    const ref = String(reference || "").trim();
    if (!ref) return null;
    return cards.find(card => String(card.clip_id) === ref)
        || cards.find(card => String(card.clip_id).includes(ref)
            || String(card.shot_tag || "").includes(ref))
        || null;
}

// Returns { deck, joinIds }: the cards to render, and the clip_ids that will be joined
// in that order. Cards that cannot join (switched off, no archived video) come last and
// never appear in joinIds, so the widget only ever holds real segments.
export function resolveDeckOrder(cards, orderText, excludedIds) {
    const sorted = sortCards(cards);
    const joinable = sorted.filter(card => isJoinable(card, excludedIds));
    const rest = sorted.filter(card => !isJoinable(card, excludedIds));
    const placed = [];
    for (const reference of parseOrder(orderText)) {
        const card = findCard(joinable, reference);
        // A reference whose card is gone is dropped here; the node reports it.
        if (card && !placed.includes(card)) placed.push(card);
    }
    const ordered = placed.concat(joinable.filter(card => !placed.includes(card)));
    return {
        deck: ordered.concat(rest),
        joinIds: ordered.map(card => String(card.clip_id)),
    };
}

// moveCard is the whole drag-and-drop model: take the card out, put it back next to
// the card the pointer was over. Nothing else about the deck changes.
export function moveCard(ids, draggedId, targetId, before) {
    const original = ids || [];
    if (!original.includes(draggedId)) return [...original];
    const list = original.filter(id => id !== draggedId);
    const at = list.indexOf(targetId);
    if (at < 0) return [...original];
    list.splice(before ? at : at + 1, 0, draggedId);
    return list;
}
