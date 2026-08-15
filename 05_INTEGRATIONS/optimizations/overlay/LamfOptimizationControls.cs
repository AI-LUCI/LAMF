using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        bool created;
        using (var mutex = new Mutex(true, @"Local\LAMFOptimizationControls", out created))
        {
            if (!created)
            {
                try { EventWaitHandle.OpenExisting(@"Local\LAMFOptimizationControls.Show").Set(); }
                catch (WaitHandleCannotBeOpenedException) { }
                return;
            }
            using (var showEvent = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\LAMFOptimizationControls.Show"))
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new ControlsForm(showEvent));
            }
        }
    }
}

internal sealed class ControlsForm : Form
{
    private readonly string runtimeDir;
    private readonly string python;
    private readonly string dataDir;
    private readonly NotifyIcon tray;
    private readonly ToolTip tips = new ToolTip();
    private readonly Panel details = new Panel();
    private readonly Button expand = new Button();
    private readonly Label statusDot = new Label();
    private readonly Label message = new Label();
    private readonly Dictionary<string, CheckBox> modules = new Dictionary<string, CheckBox>();
    private bool refreshing;

    public ControlsForm(EventWaitHandle showEvent)
    {
        var overlayDir = AppDomain.CurrentDomain.BaseDirectory;
        var packageRoot = Path.GetFullPath(Path.Combine(overlayDir, @"..\..\.."));
        runtimeDir = Path.Combine(packageRoot, "runtime");
        python = Path.Combine(runtimeDir, @".venv\Scripts\python.exe");
        dataDir = Environment.GetEnvironmentVariable("LAMF_DATA_DIR") ?? Path.Combine(packageRoot, "data");

        Text = "LAMF Optimizations";
        Width = 460;
        Height = 105;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        TopMost = true;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(17, 24, 39);
        ForeColor = Color.White;

        statusDot.SetBounds(14, 19, 14, 24);
        statusDot.Font = new Font("Segoe UI", 15, FontStyle.Bold);
        Controls.Add(statusDot);

        var title = new Label { Text = "LAMF Optimizations", Font = new Font("Segoe UI", 12, FontStyle.Bold), AutoSize = true };
        title.SetBounds(34, 22, 170, 26);
        Controls.Add(title);

        var allOn = MakeButton("All On", 220, 14, 60);
        var allOff = MakeButton("All Off", 286, 14, 62);
        var toTray = MakeButton("Tray", 354, 14, 48);
        expand.Text = "\u25BC";
        expand.SetBounds(408, 14, 34, 30);
        Controls.Add(expand);

        allOn.Click += delegate { SetGlobal(true); };
        allOff.Click += delegate { SetGlobal(false); };
        toTray.Click += delegate { HideToTray(); };
        expand.Click += delegate { ToggleDetails(); };

        details.SetBounds(12, 58, 430, 380);
        details.BackColor = Color.FromArgb(31, 41, 55);
        details.Visible = false;
        Controls.Add(details);

        AddModule("active-work-awareness", "Active work awareness", "Prevent duplicate work across connected agents", 12);
        AddModule("minimal-solution", "Minimal solution", "Avoid unnecessary code and dependencies", 65);
        AddModule("selective-workflows", "Selective workflows", "Avoid unnecessary tools and orchestration", 118);
        AddModule("stale-context-guards", "Stale context guards", "Protect edits from outdated or concurrent state", 171);
        AddModule("surgical-changes", "Surgical changes", "Keep edits tightly scoped", 224);
        AddModule("verified-execution", "Verified execution", "Define and check success", 277);

        message.Text = "Changes apply to new MCP connections.";
        message.ForeColor = Color.FromArgb(156, 163, 175);
        message.SetBounds(12, 336, 320, 28);
        details.Controls.Add(message);
        var refresh = MakeButton("Refresh", 340, 332, 72, details);
        refresh.Click += delegate { RefreshState(); };

        tray = new NotifyIcon
        {
            Icon = CreateTrayIcon(),
            Text = "LAMF Optimizations",
            Visible = true
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("Open LAMF Optimizations", null, delegate { RestoreFromTray(); });
        menu.Items.Add("Exit and turn optimizations off", null, delegate { ExitAndDisable(); });
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += delegate { RestoreFromTray(); };
        FormClosed += delegate { tray.Visible = false; tray.Dispose(); menu.Dispose(); };
        Resize += delegate { if (WindowState == FormWindowState.Minimized) HideToTray(); };

        ThreadPool.RegisterWaitForSingleObject(showEvent, delegate
        {
            if (!IsDisposed) BeginInvoke((MethodInvoker)delegate { RestoreFromTray(); });
        }, null, Timeout.Infinite, false);
        Shown += delegate { RefreshState(); };
    }

    private Button MakeButton(string text, int x, int y, int width, Control parent = null)
    {
        var button = new Button { Text = text, BackColor = Color.White, ForeColor = Color.FromArgb(17, 24, 39), FlatStyle = FlatStyle.Flat };
        button.SetBounds(x, y, width, 30);
        (parent ?? this).Controls.Add(button);
        return button;
    }

    private void AddModule(string id, string label, string description, int y)
    {
        var box = new CheckBox { Text = label, AutoSize = true, ForeColor = Color.White, Font = new Font("Segoe UI", 10) };
        box.SetBounds(12, y, 230, 24);
        var note = new Label { Text = description, AutoSize = true, ForeColor = Color.FromArgb(156, 163, 175) };
        note.SetBounds(34, y + 25, 340, 20);
        details.Controls.Add(box);
        details.Controls.Add(note);
        modules[id] = box;
        box.Click += delegate
        {
            if (refreshing) return;
            try { Run("optimizations " + (box.Checked ? "enable " : "disable ") + id); RefreshState(); }
            catch (Exception ex) { ShowError(ex); }
        };
    }

    private void SetGlobal(bool enabled)
    {
        try { Run("optimizations " + (enabled ? "on" : "off")); RefreshState(); }
        catch (Exception ex) { ShowError(ex); }
    }

    private string Run(string arguments)
    {
        if (!File.Exists(python)) throw new FileNotFoundException("LAMF Python runtime not found", python);
        var psi = new ProcessStartInfo(python, "-m lamf.cli " + arguments + " --data-dir \"" + dataDir + "\"")
        {
            WorkingDirectory = runtimeDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        using (var process = Process.Start(psi))
        {
            var output = process.StandardOutput.ReadToEnd();
            var error = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0) throw new InvalidOperationException(error.Length > 0 ? error : output);
            return output;
        }
    }

    private void RefreshState()
    {
        try
        {
            refreshing = true;
            var state = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(Run("optimizations status"));
            var enabled = Convert.ToBoolean(state["enabled"]);
            statusDot.Text = "\u25CF";
            statusDot.ForeColor = enabled ? Color.LimeGreen : Color.OrangeRed;
            tips.SetToolTip(statusDot, enabled ? "Optimizations globally enabled" : "Optimizations globally disabled");
            foreach (Dictionary<string, object> item in (object[])state["modules"])
            {
                var id = Convert.ToString(item["id"]);
                if (!modules.ContainsKey(id)) continue;
                modules[id].Checked = Convert.ToBoolean(item["enabled"]);
                modules[id].Enabled = enabled && Convert.ToBoolean(item["valid"]);
            }
            message.Text = "Ready. Changes apply to new MCP connections.";
        }
        catch (Exception ex) { ShowError(ex); }
        finally { refreshing = false; }
    }

    private void ShowError(Exception ex)
    {
        statusDot.Text = "\u25CF";
        statusDot.ForeColor = Color.Gold;
        var text = ex.Message.Replace(Environment.NewLine, " ");
        message.Text = text.Length > 90 ? text.Substring(0, 90) + "..." : text;
        tips.SetToolTip(statusDot, ex.Message);
    }

    private void ToggleDetails()
    {
        details.Visible = !details.Visible;
        expand.Text = details.Visible ? "\u25B2" : "\u25BC";
        Height = details.Visible ? 495 : 105;
    }

    private void HideToTray()
    {
        Hide();
        tray.Visible = true;
        tray.ShowBalloonTip(1500, "LAMF Optimizations", "Running in the notification area. Double-click the green L to restore.", ToolTipIcon.Info);
    }

    private void RestoreFromTray()
    {
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
    }

    private void ExitAndDisable()
    {
        try
        {
            Run("optimizations off");
            tray.Visible = false;
            Close();
        }
        catch (Exception ex)
        {
            RestoreFromTray();
            ShowError(ex);
        }
    }

    private static Icon CreateTrayIcon()
    {
        using (var bitmap = new Bitmap(32, 32))
        using (var graphics = Graphics.FromImage(bitmap))
        using (var background = new SolidBrush(Color.FromArgb(17, 24, 39)))
        using (var font = new Font("Segoe UI", 16, FontStyle.Bold, GraphicsUnit.Pixel))
        {
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            graphics.FillEllipse(background, 1, 1, 30, 30);
            graphics.DrawString("L", font, Brushes.LimeGreen, 9, 6);
            return Icon.FromHandle(bitmap.GetHicon());
        }
    }
}
