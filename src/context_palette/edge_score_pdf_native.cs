// Fixed score adapter: native ownership and non-blocking UIA invocation.
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Automation;

public sealed class ContextPaletteScoreInvocation
{
    public volatile bool Finished;
    public volatile bool Failed;
}

public static class ContextPaletteScoreNative
{
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr hwnd, uint command);
    [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

    public static int WindowProcessId(IntPtr hwnd)
    {
        uint processId;
        return hwnd != IntPtr.Zero && GetWindowThreadProcessId(hwnd, out processId) != 0
            ? (int)processId : 0;
    }

    public static bool SourceIsCurrent(IntPtr source, int processId)
    {
        uint owner;
        return source != IntPtr.Zero && IsWindow(source) && IsWindowVisible(source)
            && GetAncestor(source, 2) == source
            && GetWindowThreadProcessId(source, out owner) != 0
            && owner == (uint)processId;
    }

    public static bool IsOwnedBy(IntPtr source, IntPtr candidate)
    {
        if (source == IntPtr.Zero || candidate == IntPtr.Zero || !IsWindow(candidate))
            return false;
        candidate = GetAncestor(candidate, 2);
        for (int depth = 0; depth < 16 && candidate != IntPtr.Zero; depth++)
        {
            if (candidate == source) return true;
            candidate = GetWindow(candidate, 4); // GW_OWNER, not just the same process.
        }
        return false;
    }

    // Invoke can block until a modal closes. A background thread in this helper
    // lets its main thread observe the dialog. Terminating the helper terminates
    // this thread too; there is no independent action process.
    // https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.invokepattern.invoke
    public static ContextPaletteScoreInvocation InvokeAsync(
        AutomationElement element, IntPtr source, int processId, IntPtr foreground)
    {
        var invocation = new ContextPaletteScoreInvocation();
        var worker = new Thread(() =>
        {
            try
            {
                var pattern = (InvokePattern)element.GetCurrentPattern(InvokePattern.Pattern);
                if (!SourceIsCurrent(source, processId)
                    || !IsOwnedBy(source, foreground)
                    || GetForegroundWindow() != foreground
                    || !element.Current.IsEnabled || element.Current.IsOffscreen)
                    throw new InvalidOperationException();
                pattern.Invoke();
            }
            catch { invocation.Failed = true; }
            finally { invocation.Finished = true; }
        });
        worker.IsBackground = true;
        worker.SetApartmentState(ApartmentState.MTA);
        worker.Start();
        return invocation;
    }
}
