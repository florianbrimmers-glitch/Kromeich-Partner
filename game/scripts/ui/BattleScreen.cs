using System.Collections.Generic;
using Godot;
using KromeichHeroes.Core;

namespace KromeichHeroes.UI;

// Auto-Battle-UI: laedt eine Demo-Armee, simuliert Kampf deterministisch,
// spielt das Event-Log in Zeitlupe ab und aktualisiert die Stack-Counter
// nach jedem Event. Minimal-Prototyp - keine Einzel-Einheit-Animationen,
// keine Hex-Positionen. Ziel: auf Handy ein Kampf laeuft von Anfang bis
// Ende durch, Spieler kann "Nochmal" (neuer Seed) oder "Zurueck" druecken.
public partial class BattleScreen : Control
{
    [Export] public NodePath Side0ContainerPath { get; set; } = "VBox/Side0Panel/Side0Stacks";
    [Export] public NodePath Side1ContainerPath { get; set; } = "VBox/Side1Panel/Side1Stacks";
    [Export] public NodePath Side0LabelPath    { get; set; } = "VBox/Side0Panel/Side0Title";
    [Export] public NodePath Side1LabelPath    { get; set; } = "VBox/Side1Panel/Side1Title";
    [Export] public NodePath LogListPath       { get; set; } = "VBox/LogScroll/LogList";
    [Export] public NodePath LogScrollPath     { get; set; } = "VBox/LogScroll";
    [Export] public NodePath StatusLabelPath   { get; set; } = "VBox/StatusLabel";
    [Export] public NodePath RematchButtonPath { get; set; } = "VBox/ButtonRow/RematchBtn";
    [Export] public NodePath BackButtonPath    { get; set; } = "VBox/ButtonRow/BackBtn";

    private const double StepIntervalSeconds = 0.4;

    private readonly Dictionary<string, Label> _stackLabels = new();
    private List<BattleEvent> _events = new();
    private int _eventIndex;
    private double _accum;
    private ulong _seed = 42;
    private List<BattleStack> _side0 = new();
    private List<BattleStack> _side1 = new();

    public override void _Ready()
    {
        GetNode<Button>(RematchButtonPath).Pressed += OnRematch;
        GetNode<Button>(BackButtonPath).Pressed += OnBack;
        StartBattle(_seed);
    }

    private void StartBattle(ulong seed)
    {
        _eventIndex = 0;
        _accum = 0;
        ClearChildren(GetNode<Container>(Side0ContainerPath));
        ClearChildren(GetNode<Container>(Side1ContainerPath));
        ClearChildren(GetNode<Container>(LogListPath));
        _stackLabels.Clear();

        var (s0, s1, l0, l1) = DemoArmy.BuildMenVsOrks();
        _side0 = s0;
        _side1 = s1;
        GetNode<Label>(Side0LabelPath).Text = l0;
        GetNode<Label>(Side1LabelPath).Text = l1;
        BuildStackRow(_side0, GetNode<Container>(Side0ContainerPath));
        BuildStackRow(_side1, GetNode<Container>(Side1ContainerPath));

        var engine = new BattleEngine();
        // Wichtig: wir simulieren auf Clones, damit der Screen die Armeen
        // inkrementell selbst reduzieren kann, statt instant das Endergebnis
        // anzuzeigen.
        var simS0 = CloneStacks(_side0, 0);
        var simS1 = CloneStacks(_side1, 1);
        var result = engine.Simulate(simS0, simS1, new DeterministicRng(seed));
        _events = result.Events;

        GetNode<Label>(StatusLabelPath).Text = $"Seed {seed}  |  Runden {result.Turns}  |  {OutcomeLabel(result.Outcome)}";
    }

    public override void _Process(double delta)
    {
        if (_eventIndex >= _events.Count) return;
        _accum += delta;
        while (_accum >= StepIntervalSeconds && _eventIndex < _events.Count)
        {
            _accum -= StepIntervalSeconds;
            PlayEvent(_events[_eventIndex]);
            _eventIndex++;
        }
    }

    private void PlayEvent(BattleEvent ev)
    {
        UpdateStackCount(ev.TargetId, ev.TargetCountAfter);
        var line = $"R{ev.Turn}  {ev.AttackerId}  ->  {ev.TargetId}   -{ev.Damage} ({ev.TargetCountAfter})";
        AppendLogLine(line);
    }

    private void AppendLogLine(string text)
    {
        var list = GetNode<Container>(LogListPath);
        var lbl = new Label { Text = text };
        lbl.AddThemeColorOverride("font_color", new Color(0.85f, 0.85f, 0.9f));
        list.AddChild(lbl);
        // Auto-Scroll: ScrollContainer clamped ScrollVertical an die MaxValue;
        // int.MaxValue reicht. CallDeferred weil Layout erst im naechsten
        // Frame vollstaendig ist.
        var scroll = GetNodeOrNull<ScrollContainer>(LogScrollPath);
        if (scroll != null)
            scroll.SetDeferred("scroll_vertical", int.MaxValue);
    }

    private void UpdateStackCount(string unitId, int newCount)
    {
        // Stacks koennen auf beiden Seiten dieselbe unit-Id haben nur wenn
        // wir spiegelbildliche Armeen bauen; in unserer Demo nicht der Fall.
        // Der Key ist darum `unitId` allein.
        if (!_stackLabels.TryGetValue(unitId, out var lbl)) return;
        lbl.Text = $"{ShortId(unitId)}  x{newCount}";
        if (newCount <= 0)
            lbl.AddThemeColorOverride("font_color", new Color(0.4f, 0.2f, 0.2f));
    }

    private void BuildStackRow(List<BattleStack> stacks, Container host)
    {
        foreach (var s in stacks)
        {
            var box = new PanelContainer { CustomMinimumSize = new Vector2(180, 90) };
            var inner = new VBoxContainer();
            var nameLbl = new Label { Text = $"{ShortId(s.Unit.Id)}  x{s.Count}" };
            var metaLbl = new Label
            {
                Text = $"Tier {s.Unit.Tier}  HP {s.Unit.Stats.Hp}",
            };
            metaLbl.AddThemeColorOverride("font_color", new Color(0.7f, 0.7f, 0.75f));
            inner.AddChild(nameLbl);
            inner.AddChild(metaLbl);
            box.AddChild(inner);
            host.AddChild(box);
            _stackLabels[s.Unit.Id] = nameLbl;
        }
    }

    private static List<BattleStack> CloneStacks(List<BattleStack> src, int side)
    {
        var list = new List<BattleStack>(src.Count);
        foreach (var s in src) list.Add(new BattleStack(s.Unit, s.Count, side));
        return list;
    }

    private static void ClearChildren(Node n)
    {
        foreach (var c in n.GetChildren()) c.QueueFree();
    }

    private static string ShortId(string id)
    {
        var idx = id.IndexOf('_');
        return idx < 0 ? id : id[(idx + 1)..];
    }

    private static string OutcomeLabel(BattleOutcome o) => o switch
    {
        BattleOutcome.Side0Wins => "Menschen gewinnen",
        BattleOutcome.Side1Wins => "Orkstaemme gewinnen",
        _ => "Unentschieden",
    };

    private void OnRematch()
    {
        _seed += 1;
        StartBattle(_seed);
    }

    private void OnBack()
    {
        GetTree().ChangeSceneToFile("res://scenes/Main.tscn");
    }
}
