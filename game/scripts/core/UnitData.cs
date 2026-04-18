using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KromeichHeroes.Core;

public sealed class UnitStats
{
    [JsonPropertyName("att")]   public int Att   { get; set; }
    [JsonPropertyName("def")]   public int Def   { get; set; }
    [JsonPropertyName("hp")]    public int Hp    { get; set; }
    [JsonPropertyName("dmg")]   public int[] Dmg { get; set; } = new[] { 1, 1 };
    [JsonPropertyName("speed")] public int Speed { get; set; }
    [JsonPropertyName("shots")] public int Shots { get; set; }
}

public sealed class UnitData
{
    [JsonPropertyName("id")]            public string Id { get; set; } = "";
    [JsonPropertyName("faction")]       public string Faction { get; set; } = "";
    [JsonPropertyName("tier")]          public int Tier { get; set; }
    [JsonPropertyName("stats")]         public UnitStats Stats { get; set; } = new();
    [JsonPropertyName("abilities")]     public List<string> Abilities { get; set; } = new();
}

public sealed class UnitsFile
{
    [JsonPropertyName("units")] public List<UnitData> Units { get; set; } = new();
}

public static class UnitRepository
{
    public static Dictionary<string, UnitData> LoadFromFile(string path)
    {
        var json = File.ReadAllText(path);
        var file = JsonSerializer.Deserialize<UnitsFile>(json)
                   ?? throw new InvalidDataException($"Kann {path} nicht lesen");
        var dict = new Dictionary<string, UnitData>();
        foreach (var u in file.Units) dict[u.Id] = u;
        return dict;
    }
}
