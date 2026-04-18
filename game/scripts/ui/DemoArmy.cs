using System.Collections.Generic;
using Godot;
using KromeichHeroes.Core;

namespace KromeichHeroes.UI;

// Baut feste Demo-Armeen aus data/units.json fuer den Battle-Prototyp.
// Spaeter ersetzt durch dynamischen Army-Builder aus dem Weltkarten-Kontext.
public static class DemoArmy
{
    private const string UnitsPath = "res://data/units.json";

    public static (List<BattleStack> side0, List<BattleStack> side1, string label0, string label1)
        BuildMenVsOrks()
    {
        var units = LoadUnits();
        var s0 = new List<BattleStack>
        {
            new(units["men_angel"],    count: 2,  side: 0),
            new(units["men_cavalier"], count: 6,  side: 0),
            new(units["men_crusader"], count: 14, side: 0),
            new(units["men_archer"],   count: 20, side: 0),
            new(units["men_spearman"], count: 40, side: 0),
        };
        var s1 = new List<BattleStack>
        {
            new(units["ork_behemoth"], count: 2,  side: 1),
            new(units["ork_cyclops"],  count: 4,  side: 1),
            new(units["ork_ogre"],     count: 8,  side: 1),
            new(units["ork_orc"],      count: 20, side: 1),
            new(units["ork_goblin"],   count: 60, side: 1),
        };
        return (s0, s1, "Menschen", "Orkstaemme");
    }

    private static Dictionary<string, UnitData> LoadUnits()
    {
        // Fully-qualified, weil System.IO.FileAccess via ImplicitUsings sichtbar ist.
        using var f = Godot.FileAccess.Open(UnitsPath, Godot.FileAccess.ModeFlags.Read);
        if (f == null)
            throw new System.IO.FileNotFoundException($"units.json nicht gefunden: {UnitsPath}");
        var json = f.GetAsText();
        return UnitRepository.ParseFromJson(json);
    }
}
