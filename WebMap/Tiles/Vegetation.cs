using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace WebMap.Tiles
{
    // Trees, bushes and rocks, per zone.
    //
    // The world sweep hands every ZDO without a creator to Observe; the ones
    // that are vegetation are classified by prefab name (cached per prefab
    // hash, so the name lookup happens once per kind, not once per tree) and
    // collected per zone. When a sweep finishes the fresh zone lists replace
    // the published ones, and zones whose contents changed are reported so
    // the tiles over them can be re-rendered: a felled wood shows up as a
    // clearing on the next render.
    //
    // The renderer bakes these into the map tiles as shaded canopies, and the
    // 3D view fetches them per chunk as a compact binary (see Chunk).
    internal static class Vegetation
    {
        public struct Point
        {
            public float x, y, z;
            public Palette.Veg kind;
            public float size;                // 1.0 = the palette's default radius / height
        }

        internal struct Class { public Palette.Veg kind; public float size; }

        private static readonly Dictionary<int, Class> classCache = new Dictionary<int, Class>();

        // published (renderer + HTTP threads read; swapped atomically per zone)
        private static readonly ConcurrentDictionary<long, Point[]> zones = new ConcurrentDictionary<long, Point[]>();
        private static readonly ConcurrentDictionary<long, int> zoneHash = new ConcurrentDictionary<long, int>();

        // being built (main thread, during a sweep)
        private static Dictionary<long, List<Point>> building;

        public static int ZoneCount => zones.Count;
        public static int LastTrees { get; private set; }
        public static int LastRocks { get; private set; }

        public static Point[] Zone(int zx, int zz)
        {
            zones.TryGetValue(TileMath.ZoneKey(zx, zz), out var pts);
            return pts;
        }

        public static void Begin()
        {
            building = new Dictionary<long, List<Point>>(zones.Count + 64);
        }

        // Main thread. Returns true when the prefab is vegetation (so callers can stop classifying it).
        public static bool Observe(int prefabHash, Vector3 pos)
        {
            var c = Classify(prefabHash);
            if (c.kind == Palette.Veg.None) return false;
            if (building == null) return true;
            long key = TileMath.ZoneKey(TileMath.ZoneCoord(pos.x), TileMath.ZoneCoord(pos.z));
            if (!building.TryGetValue(key, out var list)) building[key] = list = new List<Point>(64);
            list.Add(new Point { x = pos.x, y = pos.y, z = pos.z, kind = c.kind, size = c.size });
            return true;
        }

        // Main thread, end of sweep. Publishes and returns the zones whose vegetation changed.
        public static List<long> Finish()
        {
            var changed = new List<long>();
            if (building == null) return changed;
            int trees = 0, rocks = 0;
            var seen = new HashSet<long>();
            foreach (var kv in building)
            {
                var list = kv.Value;
                list.Sort((a, b) => a.z != b.z ? a.z.CompareTo(b.z) : a.x.CompareTo(b.x));   // stable hash & nicer draw order
                int h = 17;
                foreach (var p in list)
                {
                    h = unchecked(h * 31 + (int)(p.x * 4) * 7 + (int)(p.z * 4) * 13 + (int)p.kind * 101 + (int)(p.size * 8));
                    if (p.kind == Palette.Veg.Rock || p.kind == Palette.Veg.Ore) rocks++;
                    else if (p.kind != Palette.Veg.Stump && p.kind != Palette.Veg.Bush && p.kind != Palette.Veg.Berry) trees++;
                }
                seen.Add(kv.Key);
                if (!zoneHash.TryGetValue(kv.Key, out int old) || old != h) changed.Add(kv.Key);
                zones[kv.Key] = list.ToArray();
                zoneHash[kv.Key] = h;
            }
            // zones that emptied out entirely
            foreach (var key in new List<long>(zones.Keys))
            {
                if (seen.Contains(key)) continue;
                zones.TryRemove(key, out _);
                zoneHash.TryRemove(key, out _);
                changed.Add(key);
            }
            LastTrees = trees; LastRocks = rocks;
            building = null;
            return changed;
        }

        private static Class Classify(int prefabHash)
        {
            if (classCache.TryGetValue(prefabHash, out var cached)) return cached;
            string n = null;
            try
            {
                var go = ZNetScene.instance != null ? ZNetScene.instance.GetPrefab(prefabHash) : null;
                if (go != null) n = go.name.ToLowerInvariant();
            }
            catch { }
            var c = ClassifyName(n);
            classCache[prefabHash] = c;
            return c;
        }

        // Public for tests and for the structure classifier's "is this a plant" check.
        internal static Class ClassifyName(string n)
        {
            var c = new Class { kind = Palette.Veg.None, size = 1f };
            if (string.IsNullOrEmpty(n)) return c;
            bool small = n.Contains("small") || n.Contains("_sapling") || n.Contains("sapling");
            if (n.Contains("sapling")) return c;                              // player-planted saplings are pieces, and tiny
            if (n.Contains("_stub") || n.Contains("stubbe")) { c.kind = Palette.Veg.Stump; return c; }
            if (n.Contains("_log") || n.EndsWith("logs") || n.Contains("_trunk")) return c;   // felled wood on the ground: not a canopy

            if (n.StartsWith("beech")) { c.kind = Palette.Veg.Deciduous; c.size = small ? 0.45f : 1f; return c; }
            if (n.StartsWith("oak")) { c.kind = Palette.Veg.Deciduous; c.size = 1.7f; return c; }
            if (n.StartsWith("birch")) { c.kind = Palette.Veg.Deciduous; c.size = 0.8f; return c; }
            if (n.StartsWith("firtree")) { c.kind = Palette.Veg.Conifer; c.size = small ? 0.5f : 1f; return c; }
            if (n.StartsWith("pinetree") || n.StartsWith("pine")) { c.kind = Palette.Veg.Conifer; c.size = 1.25f; return c; }
            if (n.StartsWith("swamptree")) { c.kind = Palette.Veg.SwampTree; c.size = 1f; return c; }
            if (n.StartsWith("yggashoot")) { c.kind = Palette.Veg.MistTree; c.size = small ? 0.5f : 1f; return c; }
            if (n.Contains("ashlandstree") || n.Contains("ashtree") || n.Contains("charredtree")) { c.kind = Palette.Veg.AshTree; return c; }
            if (n.Contains("deadtree") || n.Contains("dead_tree")) { c.kind = Palette.Veg.DeadTree; return c; }
            if (n.Contains("raspberry") || n.Contains("blueberry") || n.Contains("cloudberry")) { c.kind = Palette.Veg.Berry; return c; }
            if (n.StartsWith("bush") || n.Contains("shrub")) { c.kind = Palette.Veg.Bush; return c; }
            if (n.Contains("silvervein") || n.Contains("mudpile") || n.Contains("_copper") || n.Contains("minerock") || n.Contains("_tin") || n.Contains("meteorite")) { c.kind = Palette.Veg.Ore; c.size = n.Contains("_tin") || n.Contains("mudpile") ? 0.4f : 1.2f; return c; }
            if (n.StartsWith("cliff") || n.StartsWith("giant_")) { c.kind = Palette.Veg.Rock; c.size = 2.2f; return c; }
            if (n.StartsWith("rock") || n.StartsWith("highrock") || n.StartsWith("rock_"))
            {
                c.kind = Palette.Veg.Rock;
                // rock4 / rock_4 are the big walkable boulders; rock1..3 the small ones; "_destructible" chunks are tiny
                c.size = n.Contains("rock4") || n.Contains("rock_4") || n.Contains("highrock") ? 1.6f
                       : n.Contains("frac") || n.Contains("destructible") || n.Contains("_small") ? 0.35f : 0.8f;
                return c;
            }
            if (n.Contains("tree")) { c.kind = Palette.Veg.Conifer; c.size = small ? 0.5f : 1f; return c; }   // something new: draw it as a tree
            return c;
        }

        // Binary chunk for the 3D view and the vegetation vector layer.
        // Little-endian: uint32 magic 'VEG1', uint32 count, then per point:
        //   int16 x*4 (relative to chunk min x, quarter metres), int16 z*4, int16 y*4 (absolute), uint8 kind, uint8 size*32
        public static byte[] Chunk(int cx, int cz)
        {
            float minX = TileMath.ChunkMin(cx), minZ = TileMath.ChunkMin(cz);
            float maxX = minX + TileMath.CHUNK_SIZE, maxZ = minZ + TileMath.CHUNK_SIZE;
            int zx0 = TileMath.ZoneCoord(minX), zx1 = TileMath.ZoneCoord(maxX - 0.01f);
            int zz0 = TileMath.ZoneCoord(minZ), zz1 = TileMath.ZoneCoord(maxZ - 0.01f);
            var pts = new List<Point>();
            for (int zz = zz0; zz <= zz1; zz++)
                for (int zx = zx0; zx <= zx1; zx++)
                {
                    var arr = Zone(zx, zz);
                    if (arr == null) continue;
                    foreach (var p in arr)
                        if (p.x >= minX && p.x < maxX && p.z >= minZ && p.z < maxZ) pts.Add(p);
                }
            using (var ms = new MemoryStream(8 + pts.Count * 8))
            using (var bw = new BinaryWriter(ms))
            {
                bw.Write((byte)'V'); bw.Write((byte)'E'); bw.Write((byte)'G'); bw.Write((byte)'1');
                bw.Write(pts.Count);
                foreach (var p in pts)
                {
                    bw.Write((short)Math.Round((p.x - minX) * 4));
                    bw.Write((short)Math.Round((p.z - minZ) * 4));
                    bw.Write((short)Math.Max(-32768, Math.Min(32767, Math.Round(p.y * 4))));
                    bw.Write((byte)p.kind);
                    bw.Write((byte)Math.Max(1, Math.Min(255, Math.Round(p.size * 32))));
                }
                bw.Flush();
                return ms.ToArray();
            }
        }
    }
}
