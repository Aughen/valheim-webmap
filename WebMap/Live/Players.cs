using System;
using System.Collections.Generic;
using UnityEngine;
using WebMap.Tiles;
using WebMap.Util;
using WebMap.World;

namespace WebMap.Live
{
    // The live player snapshot.
    //
    // Built on the main thread once per update interval from ZNet's peer list
    // and each player's ZDO; every other thread only ever reads the JSON
    // string this produces. A player who has not enabled "visible to other
    // players" on the in-game map is listed but sent without a position
    // (unless the server is configured to ignore that), and the fog is still
    // lifted where they walk when `always_map` is on, as before.
    internal static class Players
    {
        public struct Snapshot
        {
            public long id; public string key, name, biome;
            public float x, y, z, yaw, health, maxHealth;
            public bool hasPos, tracked, hidden, dead, pvp, inBed;
        }

        private static readonly List<Snapshot> current = new List<Snapshot>();
        private static volatile string json = "{\"count\":0,\"players\":[]}";
        private static readonly Dictionary<long, string> keyByPeer = new Dictionary<long, string>();
        private static readonly int hashPvp = "pvp".GetStableHashCode();
        private static readonly int hashInBed = "inBed".GetStableHashCode();
        private static readonly int hashDead = "dead".GetStableHashCode();
        private static readonly int hashHealth = "health".GetStableHashCode();
        private static readonly int hashMaxHealth = "max_health".GetStableHashCode();

        public static string Json => json;
        public static List<Snapshot> Current => current;

        // A stable identity for stats: the platform user id when the socket knows it, else the name.
        public static string KeyOf(ZNetPeer peer)
        {
            if (peer == null) return "";
            if (keyByPeer.TryGetValue(peer.m_uid, out string k)) return k;
            string key = null;
            try { key = peer.m_rpc?.GetSocket()?.GetHostName(); } catch { }
            if (string.IsNullOrEmpty(key)) key = "name:" + peer.m_playerName;
            keyByPeer[peer.m_uid] = key;
            return key;
        }

        public static void Forget(ZNetPeer peer) { if (peer != null) keyByPeer.Remove(peer.m_uid); }

        // Main thread.
        public static void Refresh(List<ZNetPeer> peers)
        {
            current.Clear();
            if (peers != null)
            {
                foreach (var peer in peers)
                {
                    if (peer == null || peer.m_server || string.IsNullOrEmpty(peer.m_playerName)) continue;
                    ZDO zdo = null;
                    try { zdo = ZDOMan.instance.GetZDO(peer.m_characterID); } catch { }
                    if (zdo == null) continue;
                    var s = new Snapshot { id = peer.m_uid, key = KeyOf(peer), name = peer.m_playerName };
                    Vector3 pos = zdo.GetPosition();
                    s.maxHealth = Mathf.Ceil(zdo.GetFloat(hashMaxHealth, 25f));
                    s.health = Mathf.Ceil(zdo.GetFloat(hashHealth, s.maxHealth));
                    if (s.maxHealth < s.health) s.maxHealth = s.health;
                    s.dead = zdo.GetBool(hashDead, false);
                    s.pvp = zdo.GetBool(hashPvp, false);
                    s.inBed = zdo.GetBool(hashInBed, false);
                    s.hidden = !peer.m_publicRefPos;
                    bool showPos = peer.m_publicRefPos || WebMapConfig.ALWAYS_VISIBLE;
                    bool trackPos = showPos || WebMapConfig.ALWAYS_MAP;
                    if (trackPos)
                    {
                        s.x = pos.x; s.y = pos.y; s.z = pos.z;
                        try { s.yaw = zdo.GetRotation().eulerAngles.y; } catch { }
                        try { s.biome = Palette.BiomeName((int)WorldGenerator.instance.GetBiome(pos.x, pos.z)); } catch { s.biome = ""; }
                    }
                    s.hasPos = showPos;
                    s.tracked = trackPos;
                    current.Add(s);
                }
            }
            json = Build();
        }

        private static string Build()
        {
            var j = new JsonWriter(256 + current.Count * 160);
            j.BeginObject();
            j.Prop("count", current.Count);
            j.Key("players").BeginArray();
            foreach (var s in current)
            {
                j.BeginObject();
                j.Prop("id", s.id).Prop("name", s.name);
                j.Prop("health", (int)s.health).Prop("maxHealth", (int)s.maxHealth);
                j.Prop("dead", s.dead).Prop("pvp", s.pvp).Prop("inBed", s.inBed).Prop("hidden", s.hidden);
                if (s.hasPos)
                {
                    j.Prop("x", s.x, 1).Prop("z", s.z, 1).Prop("y", s.y, 1).Prop("yaw", s.yaw, 0).Prop("biome", s.biome ?? "");
                }
                j.End();
            }
            j.End();
            j.End();
            return j.ToString();
        }
    }
}
