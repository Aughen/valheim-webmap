using System;
using System.IO;
using UnityEngine;
using WebMap.Tiles;
using WebMap.Util;

namespace WebMap.World
{
    // The shared explored mask ("fog of war").
    //
    // One byte per cell on the same 2048 x 12 m grid the mod has always used,
    // so an existing fog.png keeps every metre players have already uncovered
    // when upgrading. Row 0 is the SOUTH edge of the world (that is how the
    // old Texture2D was laid out); the PNG written to disk and served to the
    // browser has north at the top, like any map.
    //
    // Revealing runs on the main thread from player positions. Everything
    // else -- the tile store asking whether a square is explored, the HTTP
    // thread serving the mask -- only reads the byte array, which is safe.
    internal static class Fog
    {
        private static byte[] mask;
        private static int size, pixelSize, half;
        private static int exploredCount;
        private static volatile byte[] pngCache;
        public static bool Dirty { get; private set; }

        public static int Size => size;
        public static int PixelSize => pixelSize;

        public static void Init(int textureSize, int pixel)
        {
            size = textureSize; pixelSize = pixel; half = size / 2;
            mask = new byte[size * size];
            exploredCount = 0;
            pngCache = null;
            Dirty = false;
        }

        // Main thread: the legacy fog.png is decoded by Unity (it may be any PNG flavour the old code wrote).
        public static bool Load(string path)
        {
            try
            {
                if (!File.Exists(path)) return false;
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!ImageConv.LoadImage(tex, File.ReadAllBytes(path))) return false;
                if (tex.width != size || tex.height != size)
                {
                    ZLog.LogWarning($"WebMap: fog.png is {tex.width}x{tex.height}, expected {size}x{size}; starting a fresh fog");
                    UnityEngine.Object.Destroy(tex);
                    return false;
                }
                Color32[] px = tex.GetPixels32();      // row 0 = bottom = south
                int n = 0;
                for (int i = 0; i < px.Length; i++) { bool e = px[i].r > 127; mask[i] = e ? (byte)255 : (byte)0; if (e) n++; }
                exploredCount = n;
                UnityEngine.Object.Destroy(tex);
                pngCache = null;
                return true;
            }
            catch (Exception e)
            {
                ZLog.LogWarning("WebMap: could not read fog.png: " + e.Message);
                return false;
            }
        }

        public static void Save(string path)
        {
            try
            {
                File.WriteAllBytes(path, Png());
                Dirty = false;
            }
            catch (Exception e)
            {
                ZLog.LogError("WebMap: FAILED TO WRITE FOG FILE! " + e.Message);
            }
        }

        private static byte[] revealedPng;

        // PNG with north at the top. Cached until the mask changes.
        public static byte[] Png()
        {
            if (WebMapConfig.REVEAL_ALL)
            {
                // reveal_all: the whole world counts as explored, so the map shows no fog at all
                if (revealedPng == null) { var all = new byte[size * size]; for (int i = 0; i < all.Length; i++) all[i] = 255; revealedPng = Util.Png.Encode(all, size, size, Util.Png.Format.Gray8, fast: true); }
                return revealedPng;
            }
            byte[] c = pngCache;
            if (c != null) return c;
            byte[] flipped = new byte[mask.Length];
            for (int y = 0; y < size; y++)
                Buffer.BlockCopy(mask, (size - 1 - y) * size, flipped, y * size, size);
            c = Util.Png.Encode(flipped, size, size, Util.Png.Format.Gray8, fast: true);
            pngCache = c;
            return c;
        }

        // Main thread. Reveals a disc and reports newly uncovered cells to the tile store.
        public static int Reveal(float wx, float wz, float radius)
        {
            int r = (int)Math.Ceiling(radius / pixelSize);
            int r2 = r * r;
            int cx = Mathf.RoundToInt(wx / pixelSize + half);
            int cy = Mathf.RoundToInt(wz / pixelSize + half);
            int revealed = 0;
            for (int y = cy - r; y <= cy + r; y++)
            {
                if (y < 0 || y >= size) continue;
                for (int x = cx - r; x <= cx + r; x++)
                {
                    if (x < 0 || x >= size) continue;
                    int dx = x - cx, dy = y - cy;
                    if (dx * dx + dy * dy >= r2) continue;
                    int i = y * size + x;
                    if (mask[i] != 0) continue;
                    mask[i] = 255;
                    exploredCount++;
                    revealed++;
                    TileStore.OnExplored((x - half) * pixelSize, (y - half) * pixelSize);
                }
            }
            if (revealed > 0) { Dirty = true; pngCache = null; }
            return revealed;
        }

        // Zones the game has generated only exist where a player (or their ship) came within a few
        // zones, so the saved list is a record of everywhere anyone has been, including long before
        // this mod was installed. Reveal them, eroded by a margin so the edge lands near what the
        // players actually saw. Each zone is handled once per server run. Main thread.
        private static readonly System.Collections.Generic.HashSet<Vector2s> visitedDone = new System.Collections.Generic.HashSet<Vector2s>();
        public static int RevealVisitedZones()
        {
            if (!WebMapConfig.REVEAL_VISITED) return 0;
            System.Collections.Generic.HashSet<Vector2s> gen;
            try { gen = ZoneSystem.instance?.m_generatedZones; } catch { return 0; }
            if (gen == null || gen.Count == 0) return 0;
            int margin = Mathf.Clamp(WebMapConfig.REVEAL_VISITED_MARGIN, 0, 5);
            int zones = 0, cells = 0;
            foreach (var z in gen)
            {
                if (visitedDone.Contains(z)) continue;
                bool inside = true;
                for (int dy = -margin; dy <= margin && inside; dy++)
                    for (int dx = -margin; dx <= margin; dx++)
                        if (!gen.Contains(new Vector2s((short)(z.x + dx), (short)(z.y + dy)))) { inside = false; break; }
                if (!inside) continue;
                visitedDone.Add(z);
                zones++;
                // a zone is 64 m centred on (x*64, y*64); a 46 m disc covers its corners
                cells += Reveal(z.x * 64f, z.y * 64f, 46f);
            }
            if (zones > 0) ZLog.Log($"WebMap: revealed {zones} zones players had already visited ({cells} new cells)");
            return cells;
        }

        public static bool IsExplored(float wx, float wz)
        {
            if (mask == null) return false;
            int x = Mathf.RoundToInt(wx / pixelSize + half);
            int y = Mathf.RoundToInt(wz / pixelSize + half);
            if (x < 0 || y < 0 || x >= size || y >= size) return false;
            return mask[y * size + x] != 0;
        }

        // Any explored cell inside a world rectangle? (Used to decide whether a close-zoom tile is worth rendering.)
        public static bool AnyExplored(float minX, float minZ, float maxX, float maxZ)
        {
            if (mask == null) return false;
            int x0 = Mathf.Clamp(Mathf.FloorToInt(minX / pixelSize + half), 0, size - 1);
            int x1 = Mathf.Clamp(Mathf.CeilToInt(maxX / pixelSize + half), 0, size - 1);
            int y0 = Mathf.Clamp(Mathf.FloorToInt(minZ / pixelSize + half), 0, size - 1);
            int y1 = Mathf.Clamp(Mathf.CeilToInt(maxZ / pixelSize + half), 0, size - 1);
            for (int y = y0; y <= y1; y++)
            {
                int row = y * size;
                for (int x = x0; x <= x1; x++) if (mask[row + x] != 0) return true;
            }
            return false;
        }

        // Walk every explored cell (startup: queue the close-zoom tiles that should already exist).
        public static void ForEachExplored(Action<float, float> action, int stride = 1)
        {
            if (mask == null) return;
            for (int y = 0; y < size; y += stride)
                for (int x = 0; x < size; x += stride)
                    if (mask[y * size + x] != 0) action((x - half) * pixelSize, (y - half) * pixelSize);
        }

        public static float ExploredPercent()
        {
            // cells inside the 10 km world circle
            double worldCells = Math.PI * Math.Pow(10000.0 / pixelSize, 2);
            return (float)(100.0 * exploredCount / worldCells);
        }

        public static int ExploredCells => exploredCount;
    }
}
