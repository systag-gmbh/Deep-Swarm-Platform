#!/usr/bin/env -S dotnet run

using System;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;

var repoRoot = Environment.CurrentDirectory;
var versionPath = Path.Combine(repoRoot, "VERSION");

// Show current version if no argument
if (args.Length == 0)
{
    if (File.Exists(versionPath))
    {
        var current = File.ReadAllText(versionPath).Trim();
        Console.WriteLine($"Current version: v{current}");
    }
    else
    {
        Console.WriteLine("VERSION file not found");
    }
    Console.WriteLine("\nUsage: ./scripts/release.cs <version>");
    Console.WriteLine("Example: ./scripts/release.cs 1.1.0");
    return;
}

var newVersion = args[0].TrimStart('v');

// Validate semver format
if (!Regex.IsMatch(newVersion, @"^\d+\.\d+\.\d+$"))
{
    Console.WriteLine($"✗ Invalid version format: {newVersion}");
    Console.WriteLine("  Expected: X.Y.Z (e.g., 1.0.0, 2.1.3)");
    Environment.Exit(1);
}

// Check for uncommitted changes
var statusResult = RunGit("status --porcelain");
if (!string.IsNullOrWhiteSpace(statusResult))
{
    Console.WriteLine("✗ Working directory has uncommitted changes:");
    Console.WriteLine(statusResult);
    Console.WriteLine("\nCommit or stash changes before creating a release.");
    Environment.Exit(1);
}

// Check if tag already exists
var existingTags = RunGit("tag -l");
if (existingTags.Split('\n', StringSplitOptions.RemoveEmptyEntries).Contains($"v{newVersion}"))
{
    Console.WriteLine($"✗ Tag v{newVersion} already exists");
    Environment.Exit(1);
}

// Update VERSION file
File.WriteAllText(versionPath, newVersion + "\n");
Console.WriteLine($"✓ Updated VERSION to {newVersion}");

// Commit the change
RunGit($"add VERSION");
RunGit($"commit -m \"chore: release v{newVersion}\"");
Console.WriteLine($"✓ Committed: chore: release v{newVersion}");

// Create tag
RunGit($"tag v{newVersion}");
Console.WriteLine($"✓ Created tag: v{newVersion}");

Console.WriteLine();
Console.WriteLine("Next: git push && git push --tags");

string RunGit(string arguments)
{
    var psi = new ProcessStartInfo
    {
        FileName = "git",
        Arguments = arguments,
        WorkingDirectory = repoRoot,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false
    };

    using var process = Process.Start(psi);
    var output = process!.StandardOutput.ReadToEnd();
    var error = process.StandardError.ReadToEnd();
    process.WaitForExit();

    if (process.ExitCode != 0 && !string.IsNullOrWhiteSpace(error))
    {
        Console.WriteLine($"Git error: {error}");
    }

    return output;
}
