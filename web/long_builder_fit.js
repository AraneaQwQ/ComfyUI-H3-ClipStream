// Card sizing for the Long Builder panel: the zoom steps, the card base, and the rule for
// how tall the card area has to be. Pure functions with no DOM, so the sizing rules can be
// read and tested on their own.
//
// The rule the whole panel follows: zoom changes the cards, never the width of the node.
// The width is the size the user gave the node; the height keeps the same number of rows
// visible, which is what zooming means. Only the fit button changes the height on purpose.

export const ZOOM_STEPS = [1, 1.5, 2, 3, 4]; // 100% .. 400%, same as the Clip Bin picker
export const BASE_CARD_MIN = 150;            // px at 100%, the deck grid minimum
export const BASE_THUMB_H = 85;              // px at 100%, the card thumbnail height
export const DECK_GAP = 10;                  // px, the deck grid gap
export const MAX_ROWS = 2;                   // the fit button shows two rows, the rest scrolls
export const DECK_PAD_V = 14;                // px, the deck's own top+bottom padding

export function clampIndex(index) {
    const i = Math.round(Number(index));
    if (!Number.isFinite(i)) return 0;
    return Math.min(Math.max(i, 0), ZOOM_STEPS.length - 1);
}

export function stepIndex(index, delta) {
    return clampIndex((Number(index) || 0) + (Number(delta) || 0));
}

export function zoomFor(index) { return ZOOM_STEPS[clampIndex(index)]; }
export function zoomPercent(index) { return Math.round(zoomFor(index) * 100); }
export function cardMinFor(index) { return Math.round(BASE_CARD_MIN * zoomFor(index)); }
export function thumbHeightFor(index) { return Math.round(BASE_THUMB_H * zoomFor(index)); }

// A card is its thumbnail plus the two lines under it. The panel measures the real
// height and only falls back to this estimate.
export function rowHeightFor(index) { return thumbHeightFor(index) + 62; }

// repeat(auto-fill, minmax(cardMin, 1fr)): how many columns a width of this size shows.
export function columnsFor(width, cardMin, gap = DECK_GAP) {
    if (!(width > 0) || !(cardMin > 0)) return 0;
    return Math.max(1, Math.floor((width + gap) / (cardMin + gap)));
}

// How many whole rows a deck this tall shows. A row cut in half does not count - it is
// not something the user can read, and it is not what they asked to keep when zooming.
export function visibleRows(deckHeight, rowHeight, gap = DECK_GAP) {
    const height = Math.round(Number(deckHeight)) || 0;
    const row = Math.round(Number(rowHeight)) || 0;
    if (height <= 0 || row <= 0) return 0;
    return Math.max(0, Math.floor((height + gap) / (row + gap)));
}

// The deck height that shows a given number of whole rows.
export function heightForRowCount(rows, rowHeight, gap = DECK_GAP) {
    const count = Math.round(Number(rows)) || 0;
    const row = Math.round(Number(rowHeight)) || 0;
    if (count <= 0 || row <= 0) return 0;
    return count * row + (count - 1) * gap;
}

// Never bigger than the screen, never smaller than one row - a deck whose cards are all
// cut off is worse than a node that hangs over the edge. The number returned is the height
// of the deck *box*, so padV (the deck's own padding, clip_bin_picker.css) is part of it:
// the panel measures that box, and a plan without the padding is always a bit too short.
function clampDeckHeight(rows, options) {
    const {
        chromeHeight = 0, viewHeight = 0, row, minHeight = 200, gap = DECK_GAP, padV = 0,
    } = options || {};
    const pad = Math.max(0, Math.round(Number(padV)) || 0);
    const floorH = Math.max(0, Math.round(Number(minHeight)) || 0);
    const chrome = Math.max(0, Math.round(Number(chromeHeight)) || 0);
    const oneRow = heightForRowCount(1, row, gap) + pad;
    const room = Math.max(floorH, (Math.round(Number(viewHeight)) || 0) - chrome, oneRow);
    const desired = heightForRowCount(rows, row, gap) + pad;
    return Math.max(Math.min(desired, room), oneRow);
}

// + and -. The card height changed, so the deck has to change with it, but the view stays
// the same: the rows that were visible are still visible.
//   deckHeight      - the card area as it is now, measured before the zoom was applied
//   rowHeightBefore - one card at the old zoom (measured before the CSS changed)
//   rowHeightAfter  - one card at the new zoom (measured after the CSS changed)
// Returns the deck height to move to; the caller turns that into a node resize.
export function planZoomHeight(options) {
    const {
        deckHeight, rowHeightBefore, rowHeightAfter, chromeHeight = 0,
        viewHeight = 0, minHeight = 200, gap = DECK_GAP, padV = 0,
    } = options || {};
    const rowBefore = Math.max(40, Math.round(Number(rowHeightBefore)) || 0);
    const rowAfter = Math.max(40, Math.round(Number(rowHeightAfter)) || 0);
    const rows = Math.max(1, visibleRows(deckHeight, rowBefore, gap));
    return clampDeckHeight(rows,
        { chromeHeight, viewHeight, row: rowAfter, minHeight, gap, padV });
}

// The fit button: keep the width the node has, and make the deck tall enough for the rows
// that width produces - at most MAX_ROWS, the rest scrolls. Returns 0 when there is
// nothing to show, which tells the caller to leave the area alone.
export function planFitHeight(options) {
    const {
        count, deckWidth, zoomIdx, rowHeight, chromeHeight = 0,
        viewHeight = 0, minHeight = 200, gap = DECK_GAP, padV = 0,
    } = options || {};
    const cards = Math.max(0, Math.floor(Number(count)) || 0);
    if (cards === 0) return 0;
    const row = Math.max(40, Math.round(Number(rowHeight)) || rowHeightFor(zoomIdx));
    const columns = Math.max(1, columnsFor(deckWidth, cardMinFor(zoomIdx), gap));
    const rows = Math.max(1, Math.min(MAX_ROWS, Math.ceil(cards / columns)));
    return clampDeckHeight(rows, { chromeHeight, viewHeight, row, minHeight, gap, padV });
}
