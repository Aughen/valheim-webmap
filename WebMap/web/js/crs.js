// The map's coordinate system: the same numbers as the server's TileMath.
//
// Leaflet's "lat/lng" is used as (z, x) in Valheim world metres: north (+z)
// is up. Zoom MAX_ZOOM is one pixel per metre, matching the tile pyramid;
// zooms above it are just the max-zoom tiles scaled up by the browser.

export const WORLD_SIZE = 20480;
export const WORLD_HALF = WORLD_SIZE / 2;
export const MAX_ZOOM = 7;       // native tile zoom (1 m/px)
export const OVER_ZOOM = 10;     // how far the browser may zoom past native
export const TILE = 256;
export const WORLD_RADIUS = 10000;

export const ValheimCRS = L.extend({}, L.CRS.Simple, {
  // LonLat with its own bounds: Leaflet's stock LonLat projection is bounded to
  // +-180/90, which would clip the tile grid to a few tiles around the origin.
  projection: L.extend({}, L.Projection.LonLat, { bounds: L.bounds([-WORLD_HALF, -WORLD_HALF], [WORLD_HALF, WORLD_HALF]) }),
  transformation: new L.Transformation(1, WORLD_HALF, -1, WORLD_HALF),
  scale(zoom) { return Math.pow(2, zoom - MAX_ZOOM); },
  zoom(scale) { return Math.log(scale) / Math.LN2 + MAX_ZOOM; },
  infinite: false,
});

export const worldBounds = L.latLngBounds([-WORLD_HALF, -WORLD_HALF], [WORLD_HALF, WORLD_HALF]);

export function toLatLng(x, z) { return L.latLng(z, x); }
export function fromLatLng(ll) { return { x: ll.lng, z: ll.lat }; }
export function metersPerPixel(zoom) { return Math.pow(2, MAX_ZOOM - zoom); }
export function fmt(n) { return (Math.round(n * 10) / 10).toFixed(1); }
export function dist(a, b) { return Math.hypot(a.x - b.x, a.z - b.z); }

export function chunkOf(w) { return Math.floor((w + WORLD_HALF) / 256); }
export function chunkMin(c) { return -WORLD_HALF + c * 256; }
