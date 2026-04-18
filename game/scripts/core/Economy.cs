using System.Collections.Generic;

namespace KromeichHeroes.Core;

public sealed class Resources
{
    public int Gold { get; set; }
    public int Wood { get; set; }
    public int Ore { get; set; }
    public int Mercury { get; set; }
    public int Sulfur { get; set; }
    public int Crystal { get; set; }
    public int Gems { get; set; }

    public void Add(Resources other)
    {
        Gold += other.Gold;
        Wood += other.Wood;
        Ore += other.Ore;
        Mercury += other.Mercury;
        Sulfur += other.Sulfur;
        Crystal += other.Crystal;
        Gems += other.Gems;
    }

    public bool CanAfford(Resources cost) =>
        Gold >= cost.Gold && Wood >= cost.Wood && Ore >= cost.Ore
        && Mercury >= cost.Mercury && Sulfur >= cost.Sulfur
        && Crystal >= cost.Crystal && Gems >= cost.Gems;

    public void Subtract(Resources cost)
    {
        Gold -= cost.Gold;
        Wood -= cost.Wood;
        Ore -= cost.Ore;
        Mercury -= cost.Mercury;
        Sulfur -= cost.Sulfur;
        Crystal -= cost.Crystal;
        Gems -= cost.Gems;
    }

    public Resources Copy() => new()
    {
        Gold = Gold, Wood = Wood, Ore = Ore,
        Mercury = Mercury, Sulfur = Sulfur, Crystal = Crystal, Gems = Gems,
    };
}

public sealed class Town
{
    public int Owner { get; set; }
    public string Faction { get; init; } = "";
    public int X { get; init; }
    public int Y { get; init; }
    public Dictionary<int, int> DwellingLevels { get; init; } = new();
    public bool HasCastle { get; set; }
    public bool HasCapitol { get; set; }
    public Dictionary<string, int> AvailableUnits { get; } = new();

    public Resources DailyIncome()
    {
        int gold = HasCapitol ? 500 : (HasCastle ? 1000 : 250);
        return new Resources { Gold = gold };
    }
}

public sealed class Mine
{
    public int? Owner { get; set; }
    public string Resource { get; init; } = "gold";
    public int X { get; init; }
    public int Y { get; init; }

    public Resources DailyIncome()
    {
        var r = new Resources();
        if (Owner is null) return r;
        int amount = Resource == "gold" ? 1000 : 1;
        switch (Resource)
        {
            case "gold":    r.Gold = amount; break;
            case "wood":    r.Wood = amount; break;
            case "ore":     r.Ore = amount; break;
            case "mercury": r.Mercury = amount; break;
            case "sulfur":  r.Sulfur = amount; break;
            case "crystal": r.Crystal = amount; break;
            case "gems":    r.Gems = amount; break;
        }
        return r;
    }
}

public static class Economy
{
    public static readonly IReadOnlyDictionary<int, int> WeeklyGrowthByTier =
        new Dictionary<int, int> { {1,22},{2,12},{3,7},{4,4},{5,3},{6,2},{7,1} };

    public static void ApplyWeeklyGrowth(Town town, IReadOnlyDictionary<string, UnitData> unitsByFaction)
    {
        foreach (var (id, unit) in unitsByFaction)
        {
            if (unit.Faction != town.Faction) continue;
            int level = town.DwellingLevels.TryGetValue(unit.Tier, out var lv) ? lv : 0;
            if (level <= 0) continue;
            int baseGrowth = WeeklyGrowthByTier.TryGetValue(unit.Tier, out var g) ? g : 1;
            int amount = (int)(baseGrowth * (1.0 + 0.5 * level));
            town.AvailableUnits[id] = town.AvailableUnits.TryGetValue(id, out var have) ? have + amount : amount;
        }
    }

    public static void TickDay(
        Resources treasury,
        IList<Town> towns,
        IList<Mine> mines,
        int dayIndex,
        IReadOnlyDictionary<string, UnitData>? allUnits = null)
    {
        foreach (var t in towns) treasury.Add(t.DailyIncome());
        foreach (var m in mines) treasury.Add(m.DailyIncome());
        if (dayIndex % 7 == 1 && allUnits is not null)
            foreach (var t in towns) ApplyWeeklyGrowth(t, allUnits);
    }
}
