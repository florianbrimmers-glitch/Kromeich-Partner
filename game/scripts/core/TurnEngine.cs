using System.Collections.Generic;

namespace KromeichHeroes.Core;

// Minimal-Pendant zu tools/turn_engine.py. Haelt Player, Heroes, aktuelle Day-Nr.
// Der voll ausgearbeitete AI-Loop lebt aktuell nur im Python-Script
// (fuer CLI-Ausgabe & Balance-Sim). C#-Version erweitern, sobald Godot
// den Adventure-Screen rendert.

public sealed class HeroState
{
    public int Owner { get; init; }
    public string Name { get; init; } = "";
    public int X { get; set; }
    public int Y { get; set; }
    public int MovePoints { get; set; } = 1500;
    public List<BattleStack> Army { get; init; } = new();
    public int HeroAtt { get; set; }
    public int HeroDef { get; set; }
    public int SpellPower { get; set; } = 1;
    public int SpellPoints { get; set; } = 10;
    public List<string> Spellbook { get; init; } = new();
}

public sealed class PlayerState
{
    public int Slot { get; init; }
    public string Faction { get; init; } = "";
    public Resources Treasury { get; init; } = new() { Gold = 10000, Wood = 10, Ore = 10 };
    public List<HeroState> Heroes { get; init; } = new();
    public List<Town> Towns { get; init; } = new();
    public List<Mine> Mines { get; init; } = new();
    public bool Defeated { get; set; }
}

public sealed class GameState
{
    public int Day { get; set; } = 1;
    public List<PlayerState> Players { get; init; } = new();
    public List<Mine> UnownedMines { get; init; } = new();
    public List<MapObject> NeutralMonsters { get; init; } = new();
    public GeneratedMap? Map { get; init; }

    public int Week => (Day - 1) / 7 + 1;

    public void AdvanceDay(IReadOnlyDictionary<string, UnitData> unitsById)
    {
        foreach (var p in Players)
        {
            Economy.TickDay(p.Treasury, p.Towns, p.Mines, Day, unitsById);
            foreach (var h in p.Heroes) h.MovePoints = 1500;
        }
        // Movement / Combat via Godot-Input im Client; hier nur Tick.
        Day++;
    }

    public List<int> Winners()
    {
        var alive = new List<int>();
        foreach (var p in Players) if (!p.Defeated) alive.Add(p.Slot);
        return alive;
    }
}
