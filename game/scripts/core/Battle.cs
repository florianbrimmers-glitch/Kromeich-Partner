using System;
using System.Collections.Generic;
using System.Linq;

namespace KromeichHeroes.Core;

public sealed class BattleStack
{
    public UnitData Unit { get; }
    public int Count { get; set; }
    public int TopUnitHp { get; set; }
    public int HeroAttBonus { get; set; }
    public int HeroDefBonus { get; set; }
    public int Side { get; }

    public BattleStack(UnitData unit, int count, int side, int heroAtt = 0, int heroDef = 0)
    {
        Unit = unit;
        Count = count;
        TopUnitHp = unit.Stats.Hp;
        HeroAttBonus = heroAtt;
        HeroDefBonus = heroDef;
        Side = side;
    }

    public bool IsAlive => Count > 0;

    public int EffectiveAtt => Unit.Stats.Att + HeroAttBonus;
    public int EffectiveDef => Unit.Stats.Def + HeroDefBonus;
    public int TotalHp => (Count - 1) * Unit.Stats.Hp + TopUnitHp;

    public bool HasAbility(string a) => Unit.Abilities.Contains(a);

    public void TakeDamage(int dmg)
    {
        if (dmg <= 0) return;
        var total = TotalHp - dmg;
        if (total <= 0)
        {
            Count = 0;
            TopUnitHp = 0;
            return;
        }
        var maxHp = Unit.Stats.Hp;
        Count = ((total - 1) / maxHp) + 1;
        var remainder = total % maxHp;
        TopUnitHp = remainder == 0 ? maxHp : remainder;
    }
}

public enum BattleOutcome { Side0Wins, Side1Wins, Draw }

public sealed record BattleEvent(int Turn, string AttackerId, string TargetId, int Damage, int TargetCountAfter);

public sealed class BattleResult
{
    public BattleOutcome Outcome { get; init; }
    public int Side0Casualties { get; init; }
    public int Side1Casualties { get; init; }
    public int Turns { get; init; }
    public List<BattleEvent> Events { get; init; } = new();
}

// Deterministische, simplifizierte Kampf-Engine fuer MVP + Balance-Simulator.
// Keine Hex-Positionen, keine Spells (noch). Fokus: Schadensformel + RNG.
// Erweiterungen (Spells, Morale, Initiative-Reihenfolge) folgen in M1.
public sealed class BattleEngine
{
    private const int MaxTurns = 100;

    public BattleResult Simulate(
        List<BattleStack> side0,
        List<BattleStack> side1,
        DeterministicRng rng)
    {
        if (side0.Count == 0 || side1.Count == 0)
            return new BattleResult { Outcome = BattleOutcome.Draw };

        var side0Start = side0.Sum(s => s.Count);
        var side1Start = side1.Sum(s => s.Count);
        var events = new List<BattleEvent>();

        for (int turn = 1; turn <= MaxTurns; turn++)
        {
            var order = side0.Concat(side1)
                .Where(s => s.IsAlive)
                .OrderByDescending(s => s.Unit.Stats.Speed)
                .ThenByDescending(s => s.Count)
                .ToList();

            foreach (var attacker in order)
            {
                if (!attacker.IsAlive) continue;
                var targetPool = attacker.Side == 0 ? side1 : side0;
                var target = PickTarget(attacker, targetPool);
                if (target is null) break;

                var dmg = ComputeDamage(attacker, target, rng);
                target.TakeDamage(dmg);
                events.Add(new BattleEvent(turn, attacker.Unit.Id, target.Unit.Id, dmg, target.Count));

                if (!target.HasAbility("no_retaliation") && target.IsAlive)
                {
                    var retal = ComputeDamage(target, attacker, rng) / 2;
                    attacker.TakeDamage(retal);
                    events.Add(new BattleEvent(turn, target.Unit.Id, attacker.Unit.Id, retal, attacker.Count));
                }
            }

            var s0Alive = side0.Any(s => s.IsAlive);
            var s1Alive = side1.Any(s => s.IsAlive);
            if (!s0Alive && !s1Alive)
                return Done(BattleOutcome.Draw, side0, side1, side0Start, side1Start, turn, events);
            if (!s0Alive)
                return Done(BattleOutcome.Side1Wins, side0, side1, side0Start, side1Start, turn, events);
            if (!s1Alive)
                return Done(BattleOutcome.Side0Wins, side0, side1, side0Start, side1Start, turn, events);
        }

        return Done(BattleOutcome.Draw, side0, side1, side0Start, side1Start, MaxTurns, events);
    }

    private static BattleStack? PickTarget(BattleStack attacker, List<BattleStack> pool)
    {
        return pool.Where(s => s.IsAlive)
                   .OrderByDescending(s => Threat(attacker, s))
                   .FirstOrDefault();
    }

    private static double Threat(BattleStack attacker, BattleStack target)
    {
        var dmg = (target.Unit.Stats.Dmg[0] + target.Unit.Stats.Dmg[1]) * 0.5 * target.Count;
        return dmg / System.Math.Max(1, attacker.TotalHp);
    }

    private static int ComputeDamage(BattleStack attacker, BattleStack target, DeterministicRng rng)
    {
        var baseDmg = rng.NextInt(attacker.Unit.Stats.Dmg[0], attacker.Unit.Stats.Dmg[1]);
        var stackDmg = (long)baseDmg * attacker.Count;

        var attDiff = attacker.EffectiveAtt - target.EffectiveDef;
        double mod = 1.0;
        if (attDiff > 0)
            mod *= 1.0 + System.Math.Min(3.0, 0.05 * attDiff);
        else if (attDiff < 0)
            mod *= System.Math.Max(0.3, 1.0 + 0.025 * attDiff);

        if (attacker.HasAbility("defense_ignore_25pct"))
            mod *= 1.0 + 0.25 * System.Math.Max(0, target.EffectiveDef) / System.Math.Max(1, attacker.EffectiveAtt);
        else if (attacker.HasAbility("defense_ignore_40pct"))
            mod *= 1.0 + 0.4 * System.Math.Max(0, target.EffectiveDef) / System.Math.Max(1, attacker.EffectiveAtt);
        if (attacker.HasAbility("double_attack"))
            mod *= 1.5;
        if (attacker.HasAbility("life_drain_50pct") && attacker.IsAlive)
            mod *= 1.0;

        return (int)System.Math.Max(1, stackDmg * mod);
    }

    private static BattleResult Done(
        BattleOutcome o, List<BattleStack> s0, List<BattleStack> s1,
        int s0Start, int s1Start, int turns, List<BattleEvent> events)
    {
        return new BattleResult
        {
            Outcome = o,
            Side0Casualties = s0Start - s0.Sum(x => x.Count),
            Side1Casualties = s1Start - s1.Sum(x => x.Count),
            Turns = turns,
            Events = events,
        };
    }
}
