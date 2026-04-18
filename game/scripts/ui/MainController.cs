using Godot;

namespace KromeichHeroes.UI;

// Titel-Screen: verknuepft den "Neues Spiel"-Button mit der Battle-Szene.
// Continue ist fuer Phase-2-Multiplayer reserviert (noch disabled).
public partial class MainController : Control
{
    [Export] public NodePath NewGameButtonPath { get; set; } = "NewGameBtn";

    public override void _Ready()
    {
        var btn = GetNodeOrNull<Button>(NewGameButtonPath);
        if (btn != null)
            btn.Pressed += OnNewGamePressed;
    }

    private void OnNewGamePressed()
    {
        GetTree().ChangeSceneToFile("res://scenes/Battle.tscn");
    }
}
