using System;
using Godot;

namespace KromeichHeroes.UI;

// Titel-Screen: verknuepft den "Neues Spiel"-Button mit der Battle-Szene.
// Continue ist fuer Phase-2-Multiplayer reserviert (noch disabled).
//
// Crash-Diagnose: da Android 13+ apps keinen Zugriff mehr auf fremde Logs
// haben, fangen wir Startup-Exceptions hier ab und zeigen sie direkt im
// UI an. Zusaetzlich AppDomain-weiter Unhandled-Handler als letzte Chance.
public partial class MainController : Control
{
    [Export] public NodePath NewGameButtonPath { get; set; } = "NewGameBtn";

    public override void _Ready()
    {
        try
        {
            AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
            TaskSchedulerUnhandled();

            GD.Print("[MainController] _Ready gestartet");
            GD.Print($"[MainController] .NET Version: {Environment.Version}");
            GD.Print($"[MainController] OS: {OS.GetName()} / {OS.GetModelName()}");

            var btn = GetNodeOrNull<Button>(NewGameButtonPath);
            if (btn != null)
            {
                btn.Pressed += OnNewGamePressed;
                GD.Print("[MainController] NewGameBtn verbunden");
            }
            else
            {
                GD.PushWarning("[MainController] NewGameBtn nicht gefunden unter: " + NewGameButtonPath);
            }

            // Subtitle mit Diagnose-Info ueberschreiben, damit im Fehlerfall
            // direkt sichtbar ist, dass wir die _Ready-Phase erreicht haben.
            var subtitle = GetNodeOrNull<Label>("Subtitle");
            if (subtitle != null)
                subtitle.Text = $"MVP ok  |  .NET {Environment.Version.Major}.{Environment.Version.Minor}  |  {OS.GetName()}";
        }
        catch (Exception ex)
        {
            ShowErrorOverlay("Fehler in _Ready", ex);
        }
    }

    private static void TaskSchedulerUnhandled()
    {
        // Catch-All fuer unbeobachtete Task-Exceptions, damit die nicht
        // silent den Prozess killen.
        System.Threading.Tasks.TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            GD.PrintErr("[UnobservedTask] " + args.Exception);
            args.SetObserved();
        };
    }

    private void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        var ex = e.ExceptionObject as Exception;
        GD.PrintErr("[AppDomain.Unhandled] " + ex);
        if (ex != null)
            ShowErrorOverlay("Unhandled Exception", ex);
    }

    private void ShowErrorOverlay(string title, Exception ex)
    {
        try
        {
            var msg = $"{title}\n\n{ex.GetType().FullName}: {ex.Message}\n\n{ex.StackTrace}";
            GD.PrintErr(msg);

            // Crash-Log in user:// ablegen. Auf Android liegt das unter
            // /storage/emulated/0/Android/data/com.kromeich.heroes/files/
            // und ist per Files-App erreichbar (zumindest bis Android 11).
            using var f = Godot.FileAccess.Open("user://crash.log", Godot.FileAccess.ModeFlags.Write);
            f?.StoreString($"[{DateTime.Now:O}] {msg}\n");

            // Overlay drueber legen, damit der Nutzer den Fehler sieht.
            var overlay = new ColorRect
            {
                Color = new Color(0.1f, 0, 0, 0.95f),
                AnchorRight = 1, AnchorBottom = 1,
                MouseFilter = MouseFilterEnum.Stop,
            };
            var label = new Label
            {
                Text = msg,
                AutowrapMode = TextServer.AutowrapMode.WordSmart,
                AnchorRight = 1, AnchorBottom = 1,
                OffsetLeft = 32, OffsetTop = 64, OffsetRight = -32, OffsetBottom = -32,
            };
            label.AddThemeColorOverride("font_color", new Color(1f, 0.85f, 0.85f));
            overlay.AddChild(label);
            AddChild(overlay);
        }
        catch
        {
            // wenn selbst das Overlay failt, gibt's nichts mehr was wir tun koennen
        }
    }

    private void OnNewGamePressed()
    {
        try
        {
            GetTree().ChangeSceneToFile("res://scenes/Battle.tscn");
        }
        catch (Exception ex)
        {
            ShowErrorOverlay("Fehler beim Szenenwechsel", ex);
        }
    }
}
