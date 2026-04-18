using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KromeichHeroes.Core;

public enum Tile { Grass, Forest, Mountain, Water, Road }

public sealed class Zone
{
    public string Id { get; init; } = "";
    public string Kind { get; init; } = "";
    public int CenterX { get; init; }
    public int CenterY { get; init; }
    public int Radius { get; init; }
    public int? Owner { get; init; }
}

public sealed class MapObject
{
    public int X { get; init; }
    public int Y { get; init; }
    public string Kind { get; init; } = "";
    public int? Owner { get; init; }
    public Dictionary<string, object>? Meta { get; init; }
}

public sealed class GeneratedMap
{
    public int Width { get; init; }
    public int Height { get; init; }
    public Tile[,] Tiles { get; init; } = new Tile[0, 0];
    public List<MapObject> Objects { get; init; } = new();
    public ulong Seed { get; init; }
    public string TemplateId { get; init; } = "";

    public string RenderAscii()
    {
        var grid = new char[Height, Width];
        for (int y = 0; y < Height; y++)
            for (int x = 0; x < Width; x++)
                grid[y, x] = Tiles[y, x] switch
                {
                    Tile.Grass => '.',
                    Tile.Forest => 'f',
                    Tile.Mountain => '^',
                    Tile.Water => '~',
                    Tile.Road => '+',
                    _ => '?',
                };

        foreach (var o in Objects)
        {
            if (o.X < 0 || o.X >= Width || o.Y < 0 || o.Y >= Height) continue;
            grid[o.Y, o.X] = o.Kind switch
            {
                "town" => 'T',
                "mine" => 'M',
                "artifact" => 'A',
                "monster" => 'X',
                "hero" => 'H',
                _ => '?',
            };
        }

        var sb = new StringBuilder();
        for (int y = 0; y < Height; y++)
        {
            for (int x = 0; x < Width; x++) sb.Append(grid[y, x]);
            if (y + 1 < Height) sb.Append('\n');
        }
        return sb.ToString();
    }
}

// JSON-Deserialisierungs-Helfer
file sealed class TemplatesFile
{
    [JsonPropertyName("templates")] public List<TemplateDef> Templates { get; set; } = new();
}

file sealed class TemplateDef
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("size")] public int[] Size { get; set; } = new[] { 24, 24 };
    [JsonPropertyName("water_pct")] public int WaterPct { get; set; }
    [JsonPropertyName("richness")] public string Richness { get; set; } = "normal";
    [JsonPropertyName("zones")] public List<ZoneDef> Zones { get; set; } = new();
    [JsonPropertyName("connections")] public List<List<string>> Connections { get; set; } = new();
}

file sealed class ZoneDef
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("center")] public int[] Center { get; set; } = new[] { 0, 0 };
    [JsonPropertyName("radius")] public int Radius { get; set; }
    [JsonPropertyName("owner")] public int? Owner { get; set; }
}

public static class MapGen
{
    public static GeneratedMap Generate(string templatesPath, string templateId, ulong seed)
    {
        var json = File.ReadAllText(templatesPath);
        var file = JsonSerializer.Deserialize<TemplatesFile>(json)
                   ?? throw new InvalidDataException($"Cannot parse {templatesPath}");
        var tpl = file.Templates.FirstOrDefault(t => t.Id == templateId)
                  ?? throw new KeyNotFoundException($"Template '{templateId}' not in {templatesPath}");

        var rng = new DeterministicRng(seed);
        int w = tpl.Size[0], h = tpl.Size[1];
        var zones = tpl.Zones.Select(z => new Zone
        {
            Id = z.Id, Kind = z.Kind, Radius = z.Radius, Owner = z.Owner,
            CenterX = z.Center[0], CenterY = z.Center[1],
        }).ToList();

        var tiles = FillBase(w, h, zones, tpl.WaterPct, rng);
        ApplyConnections(tiles, zones, tpl.Connections);
        var objects = PlaceObjects(zones, tiles, tpl.Richness, rng);

        return new GeneratedMap
        {
            Width = w, Height = h, Tiles = tiles,
            Objects = objects, Seed = seed, TemplateId = templateId,
        };
    }

    private static Tile[,] FillBase(int w, int h, List<Zone> zones, int waterPct, DeterministicRng rng)
    {
        var tiles = new Tile[h, w];
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                tiles[y, x] = Tile.Mountain;

        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                foreach (var z in zones)
                {
                    int dx = x - z.CenterX, dy = y - z.CenterY;
                    if (dx * dx + dy * dy <= z.Radius * z.Radius)
                    {
                        tiles[y, x] = rng.NextDouble01() < 0.18 ? Tile.Forest : Tile.Grass;
                        break;
                    }
                }

        if (waterPct > 0)
        {
            int n = w * h * waterPct / 100;
            for (int i = 0; i < n; i++)
            {
                int x = rng.NextInt(0, w - 1);
                int y = rng.NextInt(0, h - 1);
                if (tiles[y, x] == Tile.Mountain) tiles[y, x] = Tile.Water;
            }
        }
        return tiles;
    }

    private static void ApplyConnections(Tile[,] tiles, List<Zone> zones, List<List<string>> connections)
    {
        var byId = zones.ToDictionary(z => z.Id);
        foreach (var conn in connections)
        {
            var a = byId[conn[0]]; var b = byId[conn[1]];
            int x = a.CenterX, y = a.CenterY;
            while (!(x == b.CenterX && y == b.CenterY))
            {
                if (x != b.CenterX) x += b.CenterX > x ? 1 : -1;
                else if (y != b.CenterY) y += b.CenterY > y ? 1 : -1;
                if (tiles[y, x] is Tile.Mountain or Tile.Water) tiles[y, x] = Tile.Road;
            }
        }
    }

    private static List<MapObject> PlaceObjects(List<Zone> zones, Tile[,] tiles, string richness, DeterministicRng rng)
    {
        int mines = richness switch { "poor" => 1, "rich" => 3, _ => 2 };
        int arts  = richness switch { "poor" => 0, "rich" => 2, _ => 1 };
        int mons  = richness switch { "poor" => 3, "rich" => 5, _ => 4 };

        var objs = new List<MapObject>();
        int h = tiles.GetLength(0), w = tiles.GetLength(1);

        foreach (var z in zones)
        {
            var used = new HashSet<(int, int)>();

            (int, int)? TryPick()
            {
                for (int i = 0; i < 60; i++)
                {
                    int x = z.CenterX + rng.NextInt(-z.Radius, z.Radius);
                    int y = z.CenterY + rng.NextInt(-z.Radius, z.Radius);
                    if (used.Contains((x, y))) continue;
                    if (x < 0 || x >= w || y < 0 || y >= h) continue;
                    var t = tiles[y, x];
                    if (t == Tile.Grass || t == Tile.Forest || t == Tile.Road) return (x, y);
                }
                return null;
            }

            if (z.Kind == "player_start")
            {
                objs.Add(new MapObject { X = z.CenterX, Y = z.CenterY, Kind = "town", Owner = z.Owner });
                used.Add((z.CenterX, z.CenterY));
                objs.Add(new MapObject { X = z.CenterX + 1, Y = z.CenterY, Kind = "hero", Owner = z.Owner });
                used.Add((z.CenterX + 1, z.CenterY));
            }

            for (int i = 0; i < mines; i++)
            {
                var p = TryPick(); if (p is null) continue;
                var resource = new[] { "gold", "wood", "ore", "crystal" }[rng.NextInt(0, 3)];
                objs.Add(new MapObject { X = p.Value.Item1, Y = p.Value.Item2, Kind = "mine", Owner = z.Owner, Meta = new() { ["resource"] = resource } });
                used.Add(p.Value);
            }
            for (int i = 0; i < arts; i++)
            {
                var p = TryPick(); if (p is null) continue;
                objs.Add(new MapObject { X = p.Value.Item1, Y = p.Value.Item2, Kind = "artifact" });
                used.Add(p.Value);
            }
            for (int i = 0; i < mons; i++)
            {
                var p = TryPick(); if (p is null) continue;
                int tier = z.Kind == "neutral_rich" ? rng.NextInt(1, 5) : rng.NextInt(1, 3);
                objs.Add(new MapObject { X = p.Value.Item1, Y = p.Value.Item2, Kind = "monster", Meta = new() { ["tier"] = tier } });
                used.Add(p.Value);
            }
        }
        return objs;
    }
}
