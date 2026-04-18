using System;

namespace KromeichHeroes.Core;

// xorshift64. Deterministisch ueber Plattformen hinweg (anders als System.Random).
public sealed class DeterministicRng
{
    private ulong _state;

    public DeterministicRng(ulong seed)
    {
        _state = seed == 0 ? 0x9E3779B97F4A7C15UL : seed;
    }

    public ulong NextU64()
    {
        var x = _state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        _state = x;
        return x;
    }

    public int NextInt(int minInclusive, int maxInclusive)
    {
        if (maxInclusive < minInclusive) throw new ArgumentException("max < min");
        var range = (ulong)(maxInclusive - minInclusive + 1);
        return minInclusive + (int)(NextU64() % range);
    }

    public double NextDouble01() => (NextU64() >> 11) * (1.0 / (1UL << 53));

    public bool Chance(double p) => NextDouble01() < p;
}
