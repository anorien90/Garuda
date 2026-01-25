let pagesCache = [];
let lastIntelHits = [];
let lastStatusData = null;

export function setPagesCache(pages = []) { pagesCache = Array.isArray(pages) ? pages : []; }
export function getPagesCache() { return pagesCache; }

export function setLastIntelHits(hits = []) { lastIntelHits = Array.isArray(hits) ? hits : []; }
export function getLastIntelHits() { return lastIntelHits; }

export function setLastStatusData(data) { lastStatusData = data || null; }
export function getLastStatusData() { return lastStatusData; }
