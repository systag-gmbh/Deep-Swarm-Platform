using System.Diagnostics;

namespace StackLib;

/// <summary>
/// Result of a command execution
/// </summary>
public record CommandResult(int ExitCode, string Output, string Error = "")
{
    public bool Success => ExitCode == 0;
}

/// <summary>
/// Executes external processes
/// </summary>
public static class ProcessRunner
{
    /// <summary>
    /// Run a command and capture output
    /// </summary>
    public static CommandResult Run(string command, string args)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;

        return new CommandResult(process.ExitCode, output, error);
    }

    /// <summary>
    /// Run a command in a specific directory with environment variables
    /// </summary>
    public static CommandResult RunInDir(
        string command,
        string args,
        string workingDir,
        Dictionary<string, string>? envVars = null,
        bool printErrors = true)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        if (envVars != null)
        {
            foreach (var env in envVars)
            {
                psi.Environment[env.Key] = env.Value;
            }
        }

        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;

        if (printErrors && !string.IsNullOrEmpty(error) && process.ExitCode != 0)
        {
            Console.WriteLine(error);
        }

        return new CommandResult(process.ExitCode, output, error);
    }

    /// <summary>
    /// Run a command with real-time output streaming and timeout support.
    /// Output lines are printed to console with indentation as they arrive.
    /// </summary>
    public static CommandResult RunStreaming(
        string command,
        string args,
        string workingDir,
        Dictionary<string, string>? envVars = null,
        int timeoutSeconds = 300)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        if (envVars != null)
        {
            foreach (var env in envVars)
            {
                psi.Environment[env.Key] = env.Value;
            }
        }

        var outputBuilder = new System.Text.StringBuilder();
        var errorBuilder = new System.Text.StringBuilder();

        using var process = Process.Start(psi);

        process!.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null)
            {
                outputBuilder.AppendLine(e.Data);
                if (!string.IsNullOrWhiteSpace(e.Data))
                    Console.WriteLine($"  {e.Data}");
            }
        };

        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null)
            {
                errorBuilder.AppendLine(e.Data);
                if (!string.IsNullOrWhiteSpace(e.Data)
                    && !e.Data.Contains("Found orphan containers"))
                    Console.WriteLine($"  {e.Data}");
            }
        };

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        var exited = process.WaitForExit(timeoutSeconds * 1000);

        if (!exited)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            return new CommandResult(-1, outputBuilder.ToString(), "Process timed out");
        }

        // Ensure async event handlers have flushed
        process.WaitForExit();

        return new CommandResult(process.ExitCode, outputBuilder.ToString(), errorBuilder.ToString());
    }
}
