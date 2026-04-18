using Godot;

namespace KromeichHeroes.UI;

// Absolut minimales C#-Script. Wenn die APK damit startet, wissen wir:
// die .NET-Runtime laeuft auf dem Geraet. Wenn nicht: Runtime-Problem.
public partial class CSharpProbe : Node
{
    public override void _Ready()
    {
        GD.Print("[CSharpProbe] C# is alive");
        var parent = GetParent<Control>();
        if (parent != null)
        {
            var lbl = parent.GetNodeOrNull<Label>("CSharpStatusLabel");
            if (lbl != null)
                lbl.Text = "C# Probe: OK (KromeichHeroes.dll geladen)";
        }
    }
}
