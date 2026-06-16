#!/usr/bin/env -S dotnet run
// v2 - streaming output, deadlock fix
#:project lib/StackLib.csproj

using StackLib;
using System.Text.RegularExpressions;

var repoRoot = Environment.CurrentDirectory;

// Git pull first
Console.WriteLine("Updating repository...");
var gitResult = ProcessRunner.RunInDir("git", "pull", repoRoot, printErrors: false);
Console.WriteLine(gitResult.Success
    ? (string.IsNullOrWhiteSpace(gitResult.Output) ? "Already up to date." : gitResult.Output.Trim())
    : "Warning: git pull failed, continuing with update...");
Console.WriteLine();

var config = ConfigLoader.LoadConfig(repoRoot);
var envVars = ConfigLoader.BuildEnvironment(repoRoot, config);

Console.WriteLine($"Project: {config.ProjectName}");

// Ensure networks exist
DockerHelpers.EnsureNetworks(config);

// Remove orphaned services (in services/ but not in config)
var servicesDir = Path.Combine(repoRoot, "services");
var servicePattern = new Regex(@"^\d{2}-");
var configuredServices = new HashSet<string>(config.Services, StringComparer.OrdinalIgnoreCase);

var allServiceDirs = Directory.GetDirectories(servicesDir)
    .Select(d => Path.GetFileName(d))
    .Where(name => servicePattern.IsMatch(name))
    .OrderBy(s => s)
    .ToList();

var orphanedServices = allServiceDirs.Where(s => !configuredServices.Contains(s)).ToList();

if (orphanedServices.Count > 0)
{
    Console.WriteLine("Removing orphaned services...");
    Console.WriteLine();

    foreach (var orphan in orphanedServices)
    {
        var serviceDir = Path.Combine(servicesDir, orphan);
        var composeFile = Path.Combine(serviceDir, "docker-compose.yml");
        var overrideFile = Path.Combine(repoRoot, "overrides", $"{orphan}.override.yml");

        if (File.Exists(composeFile))
        {
            Console.WriteLine($"▶ Removing orphaned service: {orphan}...");
            var composeArgs = DockerHelpers.BuildComposeArgs(config.ProjectName, File.Exists(overrideFile) ? overrideFile : null);
            var result = ProcessRunner.RunInDir("docker", composeArgs + " down -v", serviceDir, envVars);
            Console.WriteLine(result.Success ? $"✓ Removed {orphan}" : $"✗ Failed to remove {orphan}");
        }
        else
        {
            Console.WriteLine($"⚠ Disabled service directory: {orphan} (no compose file)");
        }
    }
    Console.WriteLine();
}

Console.WriteLine("Updating services...");
Console.WriteLine();

// Update each service (pull new images and recreate if changed)
foreach (var service in ServiceManager.GetServicesAscending(repoRoot, config))
{
    if (!service.ComposeFileExists)
    {
        Console.WriteLine($"✗ {service.Name} - docker-compose.yml not found");
        continue;
    }

    Console.WriteLine($"▶ Updating {service.Name}...");

    var composeArgs = DockerHelpers.BuildComposeArgs(config.ProjectName, service.OverrideFile);

    if (service.HasDockerfile)
    {
        // Build from Dockerfile (--pull updates base image)
        Console.WriteLine($"  Building {service.Name}...");
        ProcessRunner.RunStreaming("docker", composeArgs + " build --pull", service.ServiceDir, envVars);
    }
    else
    {
        // Pull latest images from registry
        ProcessRunner.RunStreaming("docker", composeArgs + " pull", service.ServiceDir, envVars);
    }

    // Recreate containers if needed
    var upArgs = service.HasDockerfile ? " up -d --build" : " up -d";
    var result = ProcessRunner.RunStreaming("docker", composeArgs + upArgs, service.ServiceDir, envVars);

    if (result.Success)
    {
        // Docker Compose v2 writes status to stderr, not stdout
        var status = result.Error.Contains("Recreat") ? "(recreated)" : "(no changes)";
        Console.WriteLine($"✓ {service.Name} {status}");
    }
    else
    {
        var reason = result.Error == "Process timed out" ? "timed out" : "failed";
        Console.WriteLine($"✗ {service.Name} - {reason}");
    }
    Console.WriteLine();
}

// Regenerate landing page
Console.WriteLine("Generating landing page...");
var landingResult = ProcessRunner.Run("dotnet", $"run {Path.Combine(repoRoot, "scripts", "generate-landing.cs")}");
if (!landingResult.Success)
{
    Console.WriteLine("✗ Failed to generate landing page");
}
